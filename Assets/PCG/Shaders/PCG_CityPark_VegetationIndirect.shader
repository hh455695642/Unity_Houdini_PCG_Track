Shader "PCG/CityPark/VegetationIndirect"
{
    Properties
    {
        _BaseMap ("Base Texture", 2D) = "white" {}
        _BaseTint ("Base Tint", Color) = (1, 1, 1, 1)
        _Smoothness ("Smoothness", Range(0, 1)) = 0.05
    }

    SubShader
    {
        Tags
        {
            "RenderPipeline" = "UniversalPipeline"
            "RenderType" = "Opaque"
            "Queue" = "Geometry"
        }

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        TEXTURE2D(_BaseMap); SAMPLER(sampler_BaseMap);
        StructuredBuffer<float4x4> _VisibleTransforms;

        CBUFFER_START(UnityPerMaterial)
            float4 _BaseMap_ST;
            half4 _BaseTint;
            half _Smoothness;
        CBUFFER_END

        struct Attributes
        {
            float4 positionOS : POSITION;
            half3 normalOS : NORMAL;
            float2 uv : TEXCOORD0;
            uint instanceID : SV_InstanceID;
        };

        float3 TransformParkPosition(float3 positionOS, uint instanceID)
        {
            return mul(_VisibleTransforms[instanceID], float4(positionOS, 1.0)).xyz;
        }

        half3 TransformParkNormal(half3 normalOS, uint instanceID)
        {
            float3x3 objectToWorld = (float3x3)_VisibleTransforms[instanceID];
            return normalize((half3)mul(objectToWorld, (float3)normalOS));
        }
        ENDHLSL

        Pass
        {
            Name "Forward"
            Tags { "LightMode" = "UniversalForward" }
            Cull Back
            ZWrite On
            ZTest LEqual

            HLSLPROGRAM
            #pragma target 4.5
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma multi_compile_instancing
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile_fragment _ _SHADOWS_SOFT
            #pragma multi_compile_fog
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                half3 normalWS : TEXCOORD1;
                float2 uv : TEXCOORD2;
                float4 shadowCoord : TEXCOORD3;
                half fogFactor : TEXCOORD4;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings Vert(Attributes input)
            {
                Varyings output;
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);
                output.positionWS = TransformParkPosition(input.positionOS.xyz, input.instanceID);
                output.positionCS = TransformWorldToHClip(output.positionWS);
                output.normalWS = TransformParkNormal(input.normalOS, input.instanceID);
                output.uv = TRANSFORM_TEX(input.uv, _BaseMap);
                output.shadowCoord = TransformWorldToShadowCoord(output.positionWS);
                output.fogFactor = ComputeFogFactor(output.positionCS.z);
                return output;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                half3 albedo = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, input.uv).rgb
                    * _BaseTint.rgb;
                half3 normalWS = normalize(input.normalWS);
                Light mainLight = GetMainLight(input.shadowCoord);
                half ndotl = saturate(dot(normalWS, mainLight.direction));
                half attenuation = mainLight.distanceAttenuation * mainLight.shadowAttenuation;
                half3 color = albedo * (
                    SampleSH(normalWS) + mainLight.color * ndotl * attenuation);
                half3 viewDirection = SafeNormalize(GetWorldSpaceViewDir(input.positionWS));
                half3 halfDirection = SafeNormalize(mainLight.direction + viewDirection);
                color += mainLight.color
                    * pow(saturate(dot(normalWS, halfDirection)), half(8.0))
                    * _Smoothness * attenuation;
                return half4(MixFog(color, input.fogFactor), half(1.0));
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
            #pragma target 4.5
            #pragma vertex VertDepth
            #pragma fragment FragDepth
            #pragma multi_compile_instancing

            struct DepthVaryings
            {
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            DepthVaryings VertDepth(Attributes input)
            {
                DepthVaryings output;
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);
                float3 positionWS = TransformParkPosition(input.positionOS.xyz, input.instanceID);
                output.positionCS = TransformWorldToHClip(positionWS);
                return output;
            }

            half4 FragDepth(DepthVaryings input) : SV_Target
            {
                return 0;
            }
            ENDHLSL
        }

        // No ShadowCaster by design: park trees receive lighting/shadows but
        // never expand the mobile shadow atlas draw workload.
    }

    FallBack Off
}
