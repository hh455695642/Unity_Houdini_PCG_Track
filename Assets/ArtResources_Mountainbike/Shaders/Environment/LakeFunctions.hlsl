#ifndef LAKE_FUNCTIONS_INCLUDED
#define LAKE_FUNCTIONS_INCLUDED
#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
void GetCubemap_float(float3 ViewDirWS, float3 PositionWS, float3 NormalWS, float Roughness, out float3 Cubemap)
{
    #ifdef SHADERGRAPH_PREVIEW
    Cubemap = 0;
    #else

    half3 reflectionVector = reflect(-ViewDirWS, NormalWS);
    Cubemap = GlossyEnvironmentReflection(reflectionVector, PositionWS, Roughness, 1.0, float2(0,0));
    //Cubemap = GlossyEnvironmentReflection(reflectionVector, Roughness, 1.0);

    #endif
}

/*
- Samples the Shadowmap for the Main Light, based on the World Position passed in. (Position node)
- For shadows to work in the Unlit Graph, the following keywords must be defined in the blackboard :
    - Enum Keyword, Global Multi-Compile "_MAIN_LIGHT", with entries :
        - "SHADOWS"
        - "SHADOWS_CASCADE"
        - "SHADOWS_SCREEN"
    - Boolean Keyword, Global Multi-Compile "_SHADOWS_SOFT"
- For a PBR/Lit Graph, these keywords are already handled for you.
*/
void MainLightShadows_float (float3 WorldPos, half4 Shadowmask, out float ShadowAtten){
    #ifdef SHADERGRAPH_PREVIEW
    ShadowAtten = 1;
    #else
    #if defined(_MAIN_LIGHT_SHADOWS_SCREEN) && !defined(_SURFACE_TYPE_TRANSPARENT)
    float4 shadowCoord = ComputeScreenPos(TransformWorldToHClip(WorldPos));
    #else
    float4 shadowCoord = TransformWorldToShadowCoord(WorldPos);
    #endif
    ShadowAtten = MainLightShadow(shadowCoord, WorldPos, Shadowmask, _MainLightOcclusionProbes);
    #endif
}
//------------------------------------------------------------------------------------------------------
// Shadowmask (v10+)
//------------------------------------------------------------------------------------------------------

/*
- Used to support "Shadowmask" mode in Lighting window.
- Should be sampled once in graph, then input into the Main Light Shadows and/or Additional Light subgraphs/functions.
- To work in an Unlit Graph, likely requires keywords :
    - Boolean Keyword, Global Multi-Compile "SHADOWS_SHADOWMASK" 
    - Boolean Keyword, Global Multi-Compile "LIGHTMAP_SHADOW_MIXING"
    - (also LIGHTMAP_ON, but I believe Shader Graph is already defining this one)
*/
void Shadowmask_half (float2 lightmapUV, out half4 Shadowmask){
    #ifdef SHADERGRAPH_PREVIEW
    Shadowmask = half4(1,1,1,1);
    #else
    OUTPUT_LIGHTMAP_UV(lightmapUV, unity_LightmapST, lightmapUV);
    Shadowmask = SAMPLE_SHADOWMASK(lightmapUV);
    #endif
}

half4 MyCalculateShadowMask( half4 input)
{
    // To ensure backward compatibility we have to avoid using shadowMask input, as it is not present in older shaders
    #if defined(SHADOWS_SHADOWMASK) && defined(LIGHTMAP_ON)
    half4 shadowMask = input;
    #elif !defined (LIGHTMAP_ON)
    half4 shadowMask = unity_ProbesOcclusion;
    #else
    half4 shadowMask = half4(1, 1, 1, 1);
    #endif

    return shadowMask;
}
float3 StylizedSpecular(
float specularSize,
float specularHardness,
float specularSpread,
float3 specularColor,
float3 normalWS,
float3 viewDirWS,
Light mainLight)
{
    
    // -------------------------
    // Main Light
    // -------------------------
    
    float3 lightDir = normalize(-mainLight.direction) ;

    // -------------------------
    // Phong Specular
    // -------------------------

    float3 reflectionDir = reflect(lightDir, normalWS);

    float RdotV = saturate(dot(reflectionDir, viewDirWS));

    float specPower = exp2((1 - specularSpread) * 10 + 1);

    float spec = pow(RdotV, specPower);

    // -------------------------
    // Stylized highlight shape
    // -------------------------

    float edge = 1 - specularSize;

    float smoothSpec = smoothstep(edge, edge + 0.15, spec);

    spec = lerp(spec, smoothSpec, specularHardness);

    // -------------------------
    // Final
    // -------------------------

    return spec *specularColor*mainLight.color ;

}

inline void GerstnerWave(
    float wavelength,
    float sharpness,
    float height,
    float speed,
    float3 direction,

    float3 worldPos,

    out float3 displacement,
    out float3 normal)
{
    
    float3 dir = normalize(direction);

    float k = 6.28318530 / wavelength;      // wave number
    float w = sqrt(9.8 * k);              // angular frequency

    float phase = dot(worldPos, dir * k) - w * _Time.y * speed;

    float s = sin(phase);
    float c = cos(phase);

    
    // vertical displacement
    float3 vertical = float3(0, height * c, 0);

    
    // horizontal displacement
    float Q = sharpness / (k * height);

    float horiz = s * (Q * height);

    float3 horizontal = dir * horiz;

    
    displacement = vertical - horizontal;

    
    // normal
    float wa = k * height;

    float nx = dir.x * wa * s;
    float nz = dir.z * wa * s;
    float ny = 1 - sharpness * wa * c;

    normal = normalize(float3(nx, ny, nz));
}

inline float SmoothMask(float edge, float smooth, float value)
{
    return smoothstep(edge, edge + smooth, value);
}

inline float DistanceFormCamera(float3 worldPos, float start, float spread)
{
    float dist = distance(_WorldSpaceCameraPos, worldPos);
    return saturate((dist - start) / spread);
}

inline float2 WorldSpaceYProjectUV(float3 worldPos)
{
    return worldPos.xz * 0.1;
}

inline float2 UVPanner(
    float2 uv,
    float2 speed,
    float2 tile,
    float scale)
{
    float2 tiling = tile * scale;
    float2 offset = speed * 0.1 * _Time.y;

    return uv * tiling + offset;
}

void TwoWayNormalBlend(
    float3 worldPos,
    float distanceMask,
    float normalStrength,
    float distanceStrength,
    float normalPan,
    float normalTile,
    TEXTURE2D_PARAM(normalMap, sampler_normalMap),
    out float3 unscaledNormal,
    out float3 finalNormal)
{
    // world projection
    float2 baseUV = WorldSpaceYProjectUV(worldPos);

    // 两个方向流动
    float2 uv1 = UVPanner(baseUV, -normalPan.xx * 0.5, normalTile.xx * 0.5, 1);
    float2 uv2 = UVPanner(baseUV, normalPan.xx, normalTile.xx, 1);

    // sample normal
    float3 n1 = UnpackNormal(SAMPLE_TEXTURE2D(normalMap, sampler_normalMap, uv1));
    float3 n2 = UnpackNormal(SAMPLE_TEXTURE2D(normalMap, sampler_normalMap, uv2));

    // 混合
    float3 normal = lerp(n1, n2, 0.5);

    // 距离衰减强度
    float strength = lerp(normalStrength, distanceStrength, distanceMask);

    unscaledNormal = normal;
    finalNormal = float3(normal.rg * strength,lerp(1,normal.b,saturate(strength)));
}

float DepthFadeWorldPosition(
    float depthFadeDistance,
    float2 screenUV,
    float rawDepth,
    float3 positionWS)
{
    float3 sceneWS = ComputeWorldSpacePosition(
        screenUV,
        rawDepth,
        UNITY_MATRIX_I_VP
    );

    float depth = positionWS.y - sceneWS.y;

    float fade = saturate(exp(-depth / depthFadeDistance));

    return fade;
}

void WaterRefractionScreenSpace(
    float3 normalWS,
    float farRefractionStrength,
    float refractionDistanceMask,
    float mask,
    float refractionStrength,

    float4 screenPos,
    float2 screenUV,
    float3 positionWS,

    out float3 refractedColor,
    out float2 refractedUV
)
{
    // -------------------------
    // 2 距离相机衰减
    // -------------------------
    float distMask = DistanceFormCamera(positionWS, refractionDistanceMask, 5);

    float baseStrength = mask * refractionStrength;

    float finalStrength = lerp(baseStrength, farRefractionStrength, distMask);

    // -------------------------
    // 3 折射UV偏移
    // -------------------------

    float offset = normalWS.xy * finalStrength * 0.1;

    float2 refractUV = screenUV + offset;

    // -------------------------
    // 4 检查是否穿透
    // -------------------------

    float sceneDepth = LinearEyeDepth(
        SampleSceneDepth(refractUV),
        _ZBufferParams
    );

    float waterDepth = screenPos.w;

    float depthDiff = waterDepth - sceneDepth;

    // -------------------------
    // 5 如果穿透则取消折射
    // -------------------------

    float maskStep = step(depthDiff, 0);

    refractUV = screenUV + offset * maskStep;

    // -------------------------
    // 6 采样SceneColor
    // -------------------------

    float3 sceneColor = SAMPLE_TEXTURE2D(_CameraOpaqueTexture, sampler_CameraOpaqueTexture, refractUV);

    refractedColor = sceneColor;
    refractedUV = refractUV;
}

inline float ShoreLineGenerator(
    float depthFadeDistance,
    float speed,
    float lines,
    float thickness,
    float centerMask,
    float centerMaskFade,
    float trailFade,
    float nearShoreExpand,
    float dissolve,
    Texture2D dissolveMask,
    SamplerState dissolveSampler,
    float2 maskSpeed,
    float2 maskTile,
    float maskScale,
    float lineDirectionality,

    float2 screenUV,
    float rawDepth,
    float3 worldPos
    )
{
    
    // -----------------------------
    // Depth Fade
    // -----------------------------
    
    float depthFade = DepthFadeWorldPosition(
        depthFadeDistance,
        screenUV,
        rawDepth,
        worldPos
    );

    
    // -----------------------------
    // Center mask
    // -----------------------------
    
    float center = SmoothMask(centerMask, centerMaskFade, depthFade);


    // -----------------------------
    // Shoreline lines animation
    // -----------------------------
    
    float thicknessRemap = lerp(0, -0.5, thickness);

    float anim = depthFade - speed * 0.1 * _Time.y;

    float wave = anim * lines;

    float f1 = frac(-wave);
    float f2 = frac(wave);

    float m1 = SmoothMask(thicknessRemap, 1, f1);
    float m2 = SmoothMask(thicknessRemap, 1, f2);

    float minMask = min(m1, m2);

    float dirMask = speed > 0 ? m2 : m1;

    float shoreline = lerp(minMask, dirMask, lineDirectionality);


    // -----------------------------
    // Dissolve mask
    // -----------------------------
    
    float2 uv = WorldSpaceYProjectUV(worldPos);

    uv = UVPanner(uv, maskSpeed, maskTile, maskScale);

    float dissolveTex = dissolveMask.Sample(dissolveSampler, uv).r;

    float dissolveMaskVal = 1 - dissolveTex * dissolve;

    shoreline *= dissolveMaskVal;


    // -----------------------------
    // Near shore expand
    // -----------------------------
    
    float expand = depthFade * nearShoreExpand;

    shoreline = lerp(shoreline, minMask, expand);


    // -----------------------------
    // Trail fade
    // -----------------------------
    
    float stepMask = step(0.5, shoreline);

    float fracDir = speed > 0 ? f2 : f1;

    float trail = fracDir * stepMask;

    float trailMask = lerp(stepMask, trail, trailFade);

    float inv = 1 - trailMask;

    float finalMask = saturate(center - inv);

    return finalMask;
}
void Blend_Screen(float Base, float Blend, float Opacity, out float Out)
{
    Out = 1.0 - (1.0 - Blend) * (1.0 - Base);
    Out = lerp(Base, Out, Opacity);
}
inline float4 LayerAlpha(
    float4 Layer,
    float BaseAlpha,
    float Mask,
    float Blend)
{
    float Alpha;
    Blend_Screen(BaseAlpha,Layer.w,Mask,Alpha);
    return lerp(Alpha, BaseAlpha, Blend);
}

inline float4 ColorLayerAlpha(
    float4 baseColor,
    float4 layerColor,
    float layerMask)
{
    float mask = layerMask * layerColor.a;
    return lerp(baseColor, layerColor, mask);
}



#endif
