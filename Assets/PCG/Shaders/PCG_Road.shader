Shader "PCG_Track/Road"
{
    Properties
    {
        _BaseTex ("Base Texture (Cd.rgb = 0)", 2D) = "white" {}
        _MaskRTex ("Mask R Texture (Cd.r)", 2D) = "white" {}
        _MaskGTex ("Mask G Texture (Cd.g)", 2D) = "white" {}
        _MaskBTex ("Mask B Texture (Cd.b)", 2D) = "white" {}

        _BaseTint ("Base Tint", Color) = (1, 1, 1, 1)
        _MaskRTint ("Mask R Tint", Color) = (1, 1, 1, 1)
        _MaskGTint ("Mask G Tint", Color) = (1, 1, 1, 1)
        _MaskBTint ("Mask B Tint", Color) = (1, 1, 1, 1)

        _BlendNoiseTex ("Blend Noise RGBA", 2D) = "gray" {}
        _NoiseScale ("Noise Scale", Float) = 8
        _NoiseStrength ("Noise Strength", Range(0, 1)) = 0.75
        _BlendFeather ("Blend Feather", Range(0.001, 0.5)) = 0.12
        _NoiseContrast ("Noise Contrast", Range(0.1, 4)) = 1.35
        _UseLowDistortionUV ("Use World-Planar UV (Non-Directional Layers)", Range(0, 1)) = 0
        _WorldUVTileSize ("World UV Tile Size (Meters)", Float) = 4
    }

    SubShader
    {
        Tags
        {
            "RenderPipeline" = "UniversalPipeline"
            "RenderType" = "Opaque"
            "Queue" = "Geometry"
        }

        Pass
        {
            Name "Forward"
            Tags { "LightMode" = "UniversalForward" }

            Cull Back
            ZWrite On
            ZTest LEqual

            HLSLPROGRAM
            #pragma target 2.0
            #pragma vertex VertForward
            #pragma fragment FragForward
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            TEXTURE2D(_BaseTex);         SAMPLER(sampler_BaseTex);
            TEXTURE2D(_MaskRTex);        SAMPLER(sampler_MaskRTex);
            TEXTURE2D(_MaskGTex);        SAMPLER(sampler_MaskGTex);
            TEXTURE2D(_MaskBTex);        SAMPLER(sampler_MaskBTex);
            TEXTURE2D(_BlendNoiseTex);   SAMPLER(sampler_BlendNoiseTex);

            CBUFFER_START(UnityPerMaterial)
                float4 _BaseTex_ST;
                float4 _MaskRTex_ST;
                float4 _MaskGTex_ST;
                float4 _MaskBTex_ST;
                float4 _BlendNoiseTex_ST;
                half4 _BaseTint;
                half4 _MaskRTint;
                half4 _MaskGTint;
                half4 _MaskBTint;
                half _NoiseScale;
                half _NoiseStrength;
                half _BlendFeather;
                half _NoiseContrast;
                half _UseLowDistortionUV;
                float _WorldUVTileSize;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                half3 normalOS : NORMAL;
                float2 uv : TEXCOORD0;
                // Houdini vertex uv3 maps to Unity Mesh UV2 / TEXCOORD2.
                // TEXCOORD1 remains free for generated lightmap UVs.
                float2 surfaceUV : TEXCOORD2;
                half4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                half3 normalWS : TEXCOORD0;
                float2 uv : TEXCOORD1;
                float2 surfaceUV : TEXCOORD2;
                float3 positionWS : TEXCOORD3;
                half4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings VertForward(Attributes input)
            {
                Varyings output;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

                VertexPositionInputs positionInputs = GetVertexPositionInputs(input.positionOS.xyz);
                VertexNormalInputs normalInputs = GetVertexNormalInputs(input.normalOS);

                output.positionCS = positionInputs.positionCS;
                output.positionWS = positionInputs.positionWS;
                output.normalWS = normalInputs.normalWS;
                output.uv = input.uv;
                output.surfaceUV = input.surfaceUV;
                output.color = saturate(input.color);
                return output;
            }

            half3 NormalizeMasks(half3 masks)
            {
                masks = saturate(masks);
                half sumMasks = dot(masks, half3(1, 1, 1));
                return sumMasks > half(1.0) ? masks / sumMasks : masks;
            }

            half4 BuildBaseMaskWeights(half3 masks)
            {
                masks = NormalizeMasks(masks);
                half baseWeight = saturate(half(1.0) - dot(masks, half3(1, 1, 1)));
                return half4(baseWeight, masks.r, masks.g, masks.b);
            }

            half RemapNoiseContrast(half noise)
            {
                return saturate((noise - half(0.5)) * _NoiseContrast + half(0.5));
            }

            half3 ApplyNoiseErosionToMasks(half3 masks, float2 uv)
            {
                masks = NormalizeMasks(masks);

                // Noise is runtime visual breakup only; HDA Cd.rgb remains deterministic length-segment masks.
                float2 noiseUV = uv * _NoiseScale;
                noiseUV = noiseUV * _BlendNoiseTex_ST.xy + _BlendNoiseTex_ST.zw;
                half3 noise = SAMPLE_TEXTURE2D(_BlendNoiseTex, sampler_BlendNoiseTex, noiseUV).rgb;
                noise = half3(
                    RemapNoiseContrast(noise.r),
                    RemapNoiseContrast(noise.g),
                    RemapNoiseContrast(noise.b)
                );

                half feather = max(_BlendFeather, half(0.001));
                half3 erodedMasks = half3(
                    smoothstep(noise.r - feather, noise.r + feather, masks.r),
                    smoothstep(noise.g - feather, noise.g + feather, masks.g),
                    smoothstep(noise.b - feather, noise.b + feather, masks.b)
                );

                return NormalizeMasks(lerp(masks, erodedMasks, saturate(_NoiseStrength)));
            }

            half4 FragForward(Varyings input) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);

                // UV0 is authoritative for directional road markings: keep the centre line
                // centred and continuous along the track, accepting mild bend stretching.
                float2 directionalUV = input.uv;

                // True world-planar UV for gravel / stone / grass. Treat the material value
                // as a toggle so unrelated parameterizations are never fractionally blended.
                // Keep float precision because this track spans roughly one kilometre.
                float inverseWorldTileSize = rcp(max(_WorldUVTileSize, 0.01));
                float2 worldPlanarUV = input.positionWS.xz * inverseWorldTileSize;
                half useWorldPlanarUV = step(half(0.5), saturate(_UseLowDistortionUV));
                float2 layerUV = lerp(directionalUV, worldPlanarUV, useWorldPlanarUV);
                half4 weights = BuildBaseMaskWeights(ApplyNoiseErosionToMasks(input.color.rgb, layerUV));

                half3 baseLayer = SAMPLE_TEXTURE2D(_BaseTex, sampler_BaseTex, TRANSFORM_TEX(directionalUV, _BaseTex)).rgb * _BaseTint.rgb;
                half3 maskRLayer = SAMPLE_TEXTURE2D(_MaskRTex, sampler_MaskRTex, TRANSFORM_TEX(layerUV, _MaskRTex)).rgb * _MaskRTint.rgb;
                half3 maskGLayer = SAMPLE_TEXTURE2D(_MaskGTex, sampler_MaskGTex, TRANSFORM_TEX(layerUV, _MaskGTex)).rgb * _MaskGTint.rgb;
                half3 maskBLayer = SAMPLE_TEXTURE2D(_MaskBTex, sampler_MaskBTex, TRANSFORM_TEX(layerUV, _MaskBTex)).rgb * _MaskBTint.rgb;

                half3 albedo = baseLayer * weights.r + maskRLayer * weights.g + maskGLayer * weights.b + maskBLayer * weights.a;

                half3 normalWS = normalize(input.normalWS);
                Light mainLight = GetMainLight();
                half ndotl = saturate(dot(normalWS, mainLight.direction));
                half3 ambient = SampleSH(normalWS);
                half3 litColor = albedo * (ambient + mainLight.color * ndotl);

                return half4(litColor, half(1.0));
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }

            Cull Back
            ZWrite On
            ZTest LEqual
            ColorMask 0

            HLSLPROGRAM
            #pragma target 2.0
            #pragma vertex VertDepth
            #pragma fragment FragDepth
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings VertDepth(Attributes input)
            {
                Varyings output;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                return output;
            }

            half4 FragDepth(Varyings input) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                return 0;
            }
            ENDHLSL
        }

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }

            Cull Back
            ZWrite On
            ZTest LEqual
            ColorMask 0

            HLSLPROGRAM
            #pragma target 2.0
            #pragma vertex VertShadow
            #pragma fragment FragShadow
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings VertShadow(Attributes input)
            {
                Varyings output;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                return output;
            }

            half4 FragShadow(Varyings input) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                return 0;
            }
            ENDHLSL
        }
    }

    FallBack Off
}
