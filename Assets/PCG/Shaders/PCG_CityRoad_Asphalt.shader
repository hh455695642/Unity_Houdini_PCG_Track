Shader "PCG/CityRoad/Asphalt"
{
    Properties
    {
        _BaseMap ("Asphalt Base", 2D) = "white" {}
        _AggregateMap ("Aggregate Detail", 2D) = "gray" {}
        [NoScaleOffset] _MacroMask ("Macro Mask (Linear RGBA)", 2D) = "gray" {}

        _BaseTint ("Base Tint", Color) = (1, 1, 1, 1)
        _AggregateTint ("Aggregate Tint", Color) = (0.78, 0.78, 0.78, 1)
        _DarkTint ("Dark Patch Tint", Color) = (0.62, 0.62, 0.62, 1)

        _BaseTileMeters ("Base Tile (Meters)", Float) = 4
        _AggregateTileMeters ("Aggregate Tile (Meters)", Float) = 1.5
        _MacroTileMeters ("Macro Tile (Meters)", Float) = 32
        _AggregateStrength ("Aggregate Strength", Range(0, 1)) = 0.35
        _EdgeWearStrength ("Edge Wear Strength", Range(0, 1)) = 0.5
        _DarkPatchStrength ("Dark Patch Strength", Range(0, 1)) = 0.2
        _Smoothness ("Smoothness", Range(0, 1)) = 0.25
        _SmoothnessVariation ("Smoothness Variation", Range(0, 0.5)) = 0.08
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
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma multi_compile_instancing
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile_fragment _ _SHADOWS_SOFT
            #pragma multi_compile_fog

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            TEXTURE2D(_BaseMap);      SAMPLER(sampler_BaseMap);
            TEXTURE2D(_AggregateMap); SAMPLER(sampler_AggregateMap);
            TEXTURE2D(_MacroMask);    SAMPLER(sampler_MacroMask);

            CBUFFER_START(UnityPerMaterial)
                float4 _BaseMap_ST;
                float4 _AggregateMap_ST;
                half4 _BaseTint;
                half4 _AggregateTint;
                half4 _DarkTint;
                float _BaseTileMeters;
                float _AggregateTileMeters;
                float _MacroTileMeters;
                half _AggregateStrength;
                half _EdgeWearStrength;
                half _DarkPatchStrength;
                half _Smoothness;
                half _SmoothnessVariation;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                half3 normalOS : NORMAL;
                // Houdini uv3 -> Unity Mesh UV2 / TEXCOORD2.
                float2 cityMetricUV : TEXCOORD2;
                // Cd.r is the deterministic final-boundary wear mask.
                half4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                half3 normalWS : TEXCOORD1;
                float2 cityMetricUV : TEXCOORD2;
                float4 shadowCoord : TEXCOORD3;
                half fogFactor : TEXCOORD4;
                half edgeWear : TEXCOORD5;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings Vert(Attributes input)
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
                output.cityMetricUV = input.cityMetricUV;
                output.shadowCoord = GetShadowCoord(positionInputs);
                output.fogFactor = ComputeFogFactor(positionInputs.positionCS.z);
                output.edgeWear = saturate(input.color.r);
                return output;
            }

            half3 EvaluateMobileLighting(
                half3 albedo,
                half smoothness,
                half3 normalWS,
                float3 positionWS,
                float4 shadowCoord)
            {
                Light mainLight = GetMainLight(shadowCoord);
                half ndotl = saturate(dot(normalWS, mainLight.direction));
                half attenuation = mainLight.distanceAttenuation * mainLight.shadowAttenuation;
                half3 diffuse = albedo * (SampleSH(normalWS) + mainLight.color * ndotl * attenuation);

                // Low-cost scalar specular: no normal/ORM sampling and no additional-light loop.
                half3 viewDirWS = SafeNormalize(GetWorldSpaceViewDir(positionWS));
                half3 halfDir = SafeNormalize(mainLight.direction + viewDirWS);
                half specPower = exp2(half(1.0) + smoothness * half(10.0));
                half specular = pow(saturate(dot(normalWS, halfDir)), specPower)
                    * smoothness * attenuation;
                return diffuse + mainLight.color * specular;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);

                // Fixed mobile budget: exactly three texture samples.
                float2 baseUV = input.cityMetricUV / max(_BaseTileMeters, 0.01);
                baseUV = baseUV * _BaseMap_ST.xy + _BaseMap_ST.zw;

                // A 90-degree rotation reduces visible correlation without another texture.
                float2 aggregateUV = input.cityMetricUV.yx * float2(-1.0, 1.0)
                    / max(_AggregateTileMeters, 0.01);
                aggregateUV = aggregateUV * _AggregateMap_ST.xy + _AggregateMap_ST.zw;

                float2 macroUV = input.cityMetricUV / max(_MacroTileMeters, 0.01);

                half3 baseColor = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, baseUV).rgb
                    * _BaseTint.rgb;
                half3 aggregateColor = SAMPLE_TEXTURE2D(
                    _AggregateMap, sampler_AggregateMap, aggregateUV).rgb
                    * _AggregateTint.rgb;
                half4 macroMask = SAMPLE_TEXTURE2D(_MacroMask, sampler_MacroMask, macroUV);

                half aggregateWeight = saturate(
                    macroMask.r * _AggregateStrength + input.edgeWear * _EdgeWearStrength);
                half3 albedo = lerp(baseColor, aggregateColor, aggregateWeight);
                albedo *= lerp(half3(1.0, 1.0, 1.0), _DarkTint.rgb,
                    macroMask.g * _DarkPatchStrength);

                half smoothness = saturate(
                    _Smoothness + (macroMask.b - half(0.5)) * _SmoothnessVariation);
                half3 normalWS = normalize(input.normalWS);
                half3 color = EvaluateMobileLighting(
                    albedo, smoothness, normalWS, input.positionWS, input.shadowCoord);
                color = MixFog(color, input.fogFactor);
                return half4(color, half(1.0));
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

        // No ShadowCaster pass by design. CityRoad road surfaces never write
        // the mobile shadow map; they still receive the main-light shadow in
        // Forward. This removes the self-shadow wedges and one shader variant
        // family without adding a keyword.
    }

    FallBack Off
}
