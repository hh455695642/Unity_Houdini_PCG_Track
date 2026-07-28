Shader "NewWorld/Env/Lake"
{
    Properties
    {
        [Header(Color Settings)]
        [HDR]_Color_Shallow("Color_Shallow", Color) = (0.2269659, 0.822786, 0.4507858, 0)
        [HDR]_Color_Deep("Color_Deep", Color) = (0, 0.2541522, 0.4507858, 1)
        _Water_Depth("Water_Depth", Float) = 0.3
        //[ToggleUI]_WorldSpaceDepth("WorldSpaceDepth", Float) = 1
        _DistanceMask_Start("DistanceMask_Start", Float) = 5
        _DistanceMask_Fade("DistanceMask_Fade", Float) = 10
        [ToggleUI]_ShoreFade("ShoreFade", Float) = 1
        _ShoreFade_Smoothness("ShoreFade_Smoothness", Range(0, 1)) = 0.2

        [Header(Gradation)]
        [Toggle(_ENABLEGRADATION)]_ENABLEGRADATION("EnableGradation", Float) = 0
        _GradationRange("Gradation Range",Float) = 0.8
        _Color0("Shore Color", Color) = (1,0.4,0.1,1)
        _Color1("Yellow", Color) = (1,0.9,0.2,1)
        _Color2("Green", Color) = (0.2,1,0.6,1)
        _Color3("Blue", Color) = (0.1,0.6,1,1)
        _Color4("Deep Blue", Color) = (0,0.2,0.6,1)

        [Header(Shoreline)]
        [Toggle(_ENABLESHORELINE)]_ENABLESHORELINE("EnableShoreLine", Float) = 0
        _SL_Color("SL_Color", Color) = (1, 1, 1, 1)
        _SL_WaterDepth("SL_WaterDepth", Float) = 0.3
        _SL_Speed("SL_Speed", Float) = 0.05
        _SL_Ammount("SL_Ammount", Float) = 5
        _SL_Thickness("SL_Thickness", Range(0, 1)) = 0.3
        _SL_CenterMask("SL_CenterMask", Range(0, 1)) = 0.5
        _SL_CenterMaskFade("SL_CenterMaskFade", Range(0, 1)) = 0
        [NoScaleOffset]_SL_Dissolve_Mask("SL_Dissolve_Mask", 2D) = "white" {}
        _SL_Dissolve("SL_Dissolve", Float) = 0.7
        _SL_GradientDissolve("SL_Dissolve_ShoreGradient", Range(-1, 1)) = 0
        _SL_MaskPan("SL_MaskPan", Vector) = (0.01, 0, 0, 0)
        _SL_MaskScale("SL_MaskScale", Float) = 4
        _SL_MaskTile("SL_MaskTile", Vector) = (1, 1, 0, 0)
        [ToggleUI]_SL_EnableTrail("SL_EnableTrail", Float) = 0
        _SL_Trail_Fade("SL_Trail_Fade", Range(0, 2)) = 1

        [Header(Normal Map)]
        //[Toggle(_ENABLENORMAL)]_ENABLENORMAL("EnableNormal", Float) = 0
        [Normal][NoScaleOffset]_Normal_Map("Normal_Map", 2D) = "bump" {}
        _Normal_Strength("Normal_Strength", Float) = 0.1
        _Normal_Pan("Normal_Pan", Float) = 0.1
        _Normal_Scale("Normal_Scale", Float) = 5
        _Normal_DistanceStrength("Normal_DistanceStrength", Float) = 0.01

        [Header(Lighting)]
        _ShadowColor("ShadowColor", Color) = (0, 0, 0, 0.6)
        [HDR]_Specular_Color("Specular_Color", Color) = (1, 1, 1, 1)
        _Specular_Spread("Specular_Spread", Range(0, 1)) = 0
        _Specular_Hardness("Specular_Hardness", Range(0, 1)) = 0
        _Specular_Size("Specular_Size", Range(0, 1)) = 1

        [Header(Reflection)]
        _Cubemap("Reflection Cubemap", Cube) = "" {}
        _Reflection_Strength("Reflection_Strength", Range(0, 1)) = 1
        _Reflection_Fresnel("Reflection_Fresnel", Float) = 1
        _Reflection_Distortion("Reflection_Distortion", Float) = 0

        [Header(Refraction)]
        //[Toggle(_ENABLEREFRACTION)]_ENABLEREFRACTION("EnableRefraction", Float) = 0
        _Refraction_Strength("Refraction_Strength", Float) = 0.5
        _Refraction_Distance_Strength("Refraction_Distance_Strength", Float) = 0.1
        _Refraction_Distance_Fade("Refraction_Distance_Fade", Float) = 0.5

        //        [Toggle(_ENABLECAUSTICS)]_ENABLECAUSTICS("EnableCaustics", Float) = 0
        //        _Caustics_Depth("Caustics_Depth", Float) = -4
        //        [NoScaleOffset]_Caustics_Map("Caustics_Map", 2D) = "white" {}
        //        _Caustics_Pan("Caustics_Pan", Float) = 0.1
        //        _Caustics_Scale("Caustics_Scale", Float) = 1
        //        _Caustics_Strength("Caustics_Strength", Float) = 1
        //        [NoScaleOffset]_Caustics_Distortion_Map("Caustics_Distortion_Map", 2D) = "white" {}
        //        _Caustics_Distortion_Strength("Caustics_Distortion_Strength", Float) = 3
        //        _Caustics_Distortion_Scale("Caustics_Distortion_Scale", Float) = 2
        //        _Caustics_Start("Caustics_Start", Float) = 5
        //        _Caustics_Fade("Caustics_Fade", Float) = 5
        [Header(Wave)]
        [Toggle(_ENABLEWAVE)]_ENABLEWAVE("EnableWave", Float) = 0
        _Wave_Top_Color("Wave_Top_Color", Color) = (0.2982912, 0.9207434, 0.9245283, 1)
        _1st_Wave_Length("1st_Wave_Length", Float) = 3
        _1st_Wave_Height("1st_Wave_Height", Float) = 0.01
        _1st_Wave_Speed("1st_Wave_Speed", Float) = 1
        _1st_Wave_Direction("1st_Wave_Direction", Vector) = (1, 0, 0, 0)
        _1st_Wave_Sharpness("1st_Wave_Sharpness", Float) = 0.3
        _2nd_Wave_Length("2nd_Wave_Length", Float) = 5
        _2nd_Wave_Height("2nd_Wave_Height", Float) = 0.015
        _2nd_Wave_Speed("2nd_Wave_Speed", Float) = 1.3
        _2nd_Wave_Sharpness("2nd_Wave_Sharpness", Float) = 0.3
        _2nd_Wave_Direction("2nd_Wave_Direction", Vector) = (-1, 0, 1, 0)
    }
    SubShader
    {
        Tags
        {
            "RenderPipeline"="UniversalPipeline"
            "RenderType"="Transparent"
            "UniversalMaterialType" = "Unlit"
            "Queue"="Transparent"
        }

        Pass
        {
            Name "Universal Forward"
            Cull Back
            Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
            ZTest LEqual
            ZWrite Off
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag

            #pragma shader_feature_local _ENABLESHORELINE
            #pragma shader_feature_local _ENABLEWAVE
            #pragma shader_feature_local _ENABLEGRADATION
            //#pragma shader_feature_local _ENABLEREFRACTION

            // -------------------------------------
            // Unity defined keywords
            #pragma multi_compile _ LIGHTMAP_SHADOW_MIXING
            #pragma multi_compile _ SHADOWS_SHADOWMASK
            #pragma multi_compile_fog
            // -------------------------------------
            // Universal Pipeline keywords
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            // Material Keywords
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BLENDING
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BOX_PROJECTION
            #pragma multi_compile _ _FORWARD_PLUS

            //#include "Packages/com.unity.render-pipelines.universal/Shaders/LitInput.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            //#include "Packages/com.unity.render-pipelines.core/Runtime/Utilities/Blit.hlsl"


            //--------------------------------------
            // Material Constant Buffer
            //--------------------------------------

            CBUFFER_START(UnityPerMaterial)
                float4 _Color_Shallow, _Color_Deep;

                float _Water_Depth;

                float _DistanceMask_Start, _DistanceMask_Fade;

                float _GradationRange;
                float4 _Color0, _Color1, _Color2, _Color3, _Color4;

                float _ShoreFade, _ShoreFade_Smoothness;

                float4 _SL_Color;
                float _SL_WaterDepth, _SL_Speed, _SL_Ammount, _SL_Thickness, _SL_CenterMask, _SL_CenterMaskFade,
    _SL_Dissolve, _SL_GradientDissolve, _SL_MaskScale,
    _SL_EnableTrail, _SL_Trail_Fade;
                float2 _SL_MaskPan;
                float4 _SL_MaskTile;

                float _Normal_Strength;
                float _Normal_Pan;
                float _Normal_Scale;
                float _Normal_DistanceStrength;

                float _InterSec_Edge_Fade;
                float _InterSec_Dissolve;

                float4 _Specular_Color;
                float _Specular_Size, _Specular_Hardness, _Specular_Spread;
                float4 _ShadowColor;
                ;
                float _Reflection_Strength, _Reflection_Fresnel, _Reflection_Distortion;
                float _Refraction_Distance_Strength, _Refraction_Distance_Fade, _Refraction_Strength;

                float4 _Wave_Top_Color;
                float _1st_Wave_Length, _1st_Wave_Height, _1st_Wave_Speed, _1st_Wave_Sharpness;
                float _2nd_Wave_Length, _2nd_Wave_Height, _2nd_Wave_Speed, _2nd_Wave_Sharpness;
                float4 _1st_Wave_Direction, _2nd_Wave_Direction;

            CBUFFER_END


            //--------------------------------------
            // Textures
            //--------------------------------------

            TEXTURE2D(_SurfaceDistortion_Map);
            SAMPLER(sampler_SurfaceDistortion_Map);

            TEXTURE2D(_InterSec_Foam_Mask);
            SAMPLER(sampler_InterSec_Foam_Mask);

            TEXTURE2D(_SL_Dissolve_Mask);
            SAMPLER(sampler_SL_Dissolve_Mask);

            TEXTURE2D(_Normal_Map);
            SAMPLER(sampler_Normal_Map);

            TEXTURE2D(_Caustics_Map);
            SAMPLER(sampler_Caustics_Map);

            TEXTURE2D(_Caustics_Distortion_Map);
            SAMPLER(sampler_Caustics_Distortion_Map);
            TEXTURE2D(_CameraOpaqueTexture);
            SAMPLER(sampler_CameraOpaqueTexture);
            TEXTURECUBE(_Cubemap);
            SAMPLER(sampler_Cubemap);

            //--------------------------------------
            // Function
            //--------------------------------------

            #include "Assets/ArtResources_Mountainbike/Shaders/Environment/LakeFunctions.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float4 tangentOS : TANGENT;
                float2 texcoord : TEXCOORD0;
            };

            struct Varyings
            {
                float2 uv : TEXCOORD0;
                float3 positionWS : TEXCOORD1;

                float3 normalWS : TEXCOORD2;
                half4 tangentWS : TEXCOORD3; // xyz: tangent, w: sign

                half fogFactor : TEXCOORD5;

                //float4 shadowCoord              : TEXCOORD6;
                #if defined(REQUIRES_VERTEX_SHADOW_COORD_INTERPOLATOR)
                float4 shadowCoord : TEXCOORD6;
                #endif

                //half3 viewDirWS : TEXCOORD7;
                float3 wave : TEXCOORD7;
                float4 positionCS : SV_POSITION;
                float4 positionNDC : TEXCOORD8;
            };


            Varyings vert(Attributes input)
            {
                Varyings output = (Varyings)0;

                // 先计算一次原始 worldPos
                VertexPositionInputs vertexInput = GetVertexPositionInputs(input.positionOS.xyz);

                #ifdef _ENABLEWAVE

                float3 FirstDisplacement, SecondDisplacement;
                float3 FirstNormal, SecondNormal;

                GerstnerWave(_1st_Wave_Length, _1st_Wave_Sharpness, _1st_Wave_Height, _1st_Wave_Speed,
                                         _1st_Wave_Direction, vertexInput.positionWS,
                                         FirstDisplacement, FirstNormal);

                GerstnerWave(_2nd_Wave_Length, _2nd_Wave_Sharpness, _2nd_Wave_Height, _2nd_Wave_Speed,
               _2nd_Wave_Direction, vertexInput.positionWS,
               SecondDisplacement, SecondNormal);

                float3 Displacement = FirstDisplacement + SecondDisplacement;
                output.wave = Displacement;
                input.positionOS.xyz += Displacement;

                #endif


                // 位移后重新计算一次
                vertexInput = GetVertexPositionInputs(input.positionOS.xyz);

                output.positionWS = vertexInput.positionWS;
                output.positionCS = vertexInput.positionCS;
                output.positionNDC = vertexInput.positionNDC;

                VertexNormalInputs normalInput = GetVertexNormalInputs(input.normalOS, input.tangentOS);

                output.normalWS = normalInput.normalWS;
                output.tangentWS = float4(normalInput.tangentWS, input.tangentOS.w);
                //output.viewDirWS = GetWorldSpaceNormalizeViewDir(vertexInput.positionWS);
                half fogFactor = 0;
                #if !defined(_FOG_FRAGMENT)
                fogFactor = ComputeFogFactor(vertexInput.positionCS.z);
                #endif
                output.fogFactor = fogFactor;
                output.uv = input.texcoord;
                return output;
            }

            half4 frag(Varyings input) : SV_Target
            {
                //ScreenPositon-Defaut
                //float2 screenUV = input.positionNDC.xy / input.positionNDC.w;
                float2 screenUV = GetNormalizedScreenSpaceUV(input.positionCS);

                float rawDepth = SampleSceneDepth(screenUV);

                #if !UNITY_REVERSED_Z
                rawDepth = lerp(UNITY_NEAR_CLIP_VALUE, 1, rawDepth);
                #endif

                half3 viewDirWS = GetWorldSpaceNormalizeViewDir(input.positionWS);

                float GlobalDistanceMask =
                    DistanceFormCamera(input.positionWS, _DistanceMask_Start, _DistanceMask_Fade);
                float3 NormalMap;
                float3 NormalMapUnscaled;
                TwoWayNormalBlend(input.positionWS, GlobalDistanceMask, _Normal_Strength, _Normal_DistanceStrength,
                    _Normal_Pan, _Normal_Scale, _Normal_Map,
                    sampler_Normal_Map, NormalMapUnscaled,
                    NormalMap);

                float sgn = input.tangentWS.w; // should be either +1 or -1
                float3 bitangent = sgn * cross(input.normalWS.xyz, input.tangentWS.xyz);
                half3x3 tangentToWorld = half3x3(input.tangentWS.xyz, bitangent.xyz, input.normalWS.xyz);
                float3 normalWS = NormalizeNormalPerPixel(TransformTangentToWorld(NormalMap, tangentToWorld));

                float WaterDepth_NO_Distortion = DepthFadeWorldPosition(_Water_Depth, screenUV, rawDepth,
                    input.positionWS);

                //return WaterDepth_NO_Distortion;
                float ShoreFade = SmoothMask(_ShoreFade - 1, _ShoreFade_Smoothness,
                                                     saturate(1 - WaterDepth_NO_Distortion));
                float3 RefractedColor;
                float2 RefractedUV = 0;


                float WaterDepth = DepthFadeWorldPosition(_Water_Depth, RefractedUV, rawDepth, input.positionWS);

                float4 color = lerp(_Color_Deep, _Color_Shallow, WaterDepth);

                #ifdef _ENABLEGRADATION
                
                float gradation = DepthFadeWorldPosition(_GradationRange, screenUV, rawDepth, input.positionWS);
gradation = 1 - gradation;
                float3 gradColor = _Color0.rgb;

gradColor = lerp(gradColor, _Color1.rgb, smoothstep(0.0, 0.25, gradation));
gradColor = lerp(gradColor, _Color2.rgb, smoothstep(0.25, 0.5, gradation));
gradColor = lerp(gradColor, _Color3.rgb, smoothstep(0.5, 0.75, gradation));
gradColor = lerp(gradColor, _Color4.rgb, smoothstep(0.75, 1.0, gradation));
         color.rgb =     gradColor;    
                #endif


                #ifdef _ENABLESHORELINE
                float ShoreLineMask = ShoreLineGenerator(_SL_WaterDepth, _SL_Speed, _SL_Ammount, _SL_Thickness,
                                                                        _SL_CenterMask, _SL_CenterMaskFade,
                                                                        _SL_Trail_Fade,
                                                                        _SL_GradientDissolve, _SL_Dissolve,
                                                                        _SL_Dissolve_Mask, sampler_SL_Dissolve_Mask,
                                                                        _SL_MaskPan, _SL_MaskTile, _SL_MaskScale,
                                                                        _SL_EnableTrail,
                                                                        screenUV, rawDepth, input.positionWS);
                //Shoreline
                color.rgb = ColorLayerAlpha(color, _SL_Color, ShoreLineMask).rgb;
                color.a = LayerAlpha(_SL_Color, color.a, ShoreLineMask, 0);
                #endif

                #ifdef _ENABLEWAVE
                float3 FirstDisplacement, SecondDisplacement;
                float3 FirstNormal, SecondNormal;

                GerstnerWave(_1st_Wave_Length, _1st_Wave_Sharpness, _1st_Wave_Height, _1st_Wave_Speed,
                              _1st_Wave_Direction, input.positionWS,
                              FirstDisplacement, FirstNormal);

                GerstnerWave(_2nd_Wave_Length, _2nd_Wave_Sharpness, _2nd_Wave_Height, _2nd_Wave_Speed,
                                                          _2nd_Wave_Direction, input.positionWS,
                                                          SecondDisplacement, SecondNormal);

                float3 Displacement = FirstDisplacement + SecondDisplacement;
                color.rgb = ColorLayerAlpha(color, _Wave_Top_Color, Displacement.y * 10).rgb;
                #endif
                //折射
                WaterRefractionScreenSpace(NormalMapUnscaled, _Refraction_Distance_Strength, _Refraction_Distance_Fade,
                                                ShoreFade, _Refraction_Strength,
                                                input.positionNDC, screenUV,
                                                input.positionWS,
                                                RefractedColor, RefractedUV);
                //color.w = ShoreFade * color.w;
                //#ifdef _ENABLEREFRACTION
                color.rgb = lerp(color, RefractedColor, 1 - color.w).rgb;
                color.a = ShoreFade;
                //#endif

                //反射
                float reflectionFresnel = pow((1.0 - saturate(dot(normalize(input.normalWS), normalize(viewDirWS)))),
                    _Reflection_Fresnel) * _Reflection_Strength;
                float3 ReflectionProbe;
                float3 nor = normalize(input.normalWS + NormalMap * _Reflection_Distortion);
                //GetCubemap_float(viewDirWS,input.positionWS,nor,_Reflection_Distortion,ReflectionProbe);

                // 反射方向
                float3 reflectDir = reflect(-viewDirWS, nor);

                // 采样 Cubemap
                ReflectionProbe = SAMPLE_TEXTURECUBE(_Cubemap, sampler_Cubemap, reflectDir).rgb;

                color.rgb = lerp(color.rgb, ReflectionProbe, reflectionFresnel);

                //阴影
                half4 shadowMask;
                Shadowmask_half(input.uv, shadowMask);
                float shadowAtten;
                MainLightShadows_float(input.positionWS, shadowMask, shadowAtten);
                Light mainLight = GetMainLight();

                //高光
                color.rgb += StylizedSpecular(_Specular_Size, _Specular_Hardness, _Specular_Spread, _Specular_Color,
                    normalWS, viewDirWS, mainLight);

                color.rgb = ColorLayerAlpha(color, _ShadowColor, 1 - shadowAtten);
                half fogCoord = InitializeInputDataFog(float4(input.positionWS, 1.0), input.fogFactor);
                color.rgb = MixFog(color.rgb, fogCoord);
                return float4(color);
            }
            ENDHLSL
        }
    }
}