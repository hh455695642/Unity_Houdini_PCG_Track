Shader "Mountainbike/Env/RoadBlend"
{
    Properties
    {
        [Header(Road)]
        _AsphaltAlbedo ("Asphalt Albedo (A = Opacity)", 2D) = "white" {}
        _AsphaltNormal ("Asphalt Normal", 2D) = "bump" {}
        _NormalScale ("Normal Scale", Range(0, 2)) = 1

        [Header(Edge Alpha)]
        _BlendPower ("Blend Power", Range(0.25, 8)) = 1
        _BlendOffset ("Blend Offset", Range(-1, 1)) = 0
        _AlphaCutoff ("Alpha Cutoff", Range(0, 1)) = 0.5
        _DitherWidth ("Dither Width", Range(0, 1)) = 0.12

        [Header(Realtime Main Shadow)]
        _RealtimeShadowColor ("Realtime Shadow Color (A = Strength)", Color) = (0, 0, 0, 1)
    }

    SubShader
    {
        Tags
        {
            "RenderPipeline" = "UniversalPipeline"
            "RenderType" = "AlphaTest"
            "Queue" = "AlphaTest"
        }

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }

            Blend Off
            ZWrite On
            ZTest LEqual
            Cull Back

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex ForwardVert
            #pragma fragment ForwardFrag
            #pragma multi_compile_instancing
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #include "Packages/com.unity.render-pipelines.core/ShaderLibrary/Packing.hlsl"

            TEXTURE2D(_AsphaltAlbedo); SAMPLER(sampler_AsphaltAlbedo);
            TEXTURE2D(_AsphaltNormal); SAMPLER(sampler_AsphaltNormal);

            CBUFFER_START(UnityPerMaterial)
                float4 _AsphaltAlbedo_ST;
                half _NormalScale;
                half _BlendPower;
                half _BlendOffset;
                half _AlphaCutoff;
                half _DitherWidth;
                half4 _RealtimeShadowColor;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                half3 normalOS    : NORMAL;
                half4 tangentOS   : TANGENT;
                float2 uv         : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                half3 normalWS    : TEXCOORD0;
                half4 tangentWS   : TEXCOORD1;
                float2 uv         : TEXCOORD2;
                half3 vertexSH    : TEXCOORD3;
                float3 positionWS : TEXCOORD4;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            half GetRoadAlpha(half rawAlpha)
            {
                half alpha = saturate(rawAlpha + _BlendOffset);
                return pow(alpha, max(_BlendPower, 0.0001h));
            }

            half GetScreenDither(float2 positionCS)
            {
                // Interleaved gradient noise: stable screen-space dither without texture sampling.
                float2 pixel = floor(positionCS);
                return (half)frac(52.9829189 * frac(dot(pixel, float2(0.06711056, 0.00583715))));
            }

            Varyings ForwardVert(Attributes input)
            {
                Varyings output;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

                VertexPositionInputs positionInput = GetVertexPositionInputs(input.positionOS.xyz);
                output.positionCS = positionInput.positionCS;
                output.positionWS = positionInput.positionWS;
                output.normalWS = TransformObjectToWorldNormal(input.normalOS);
                output.tangentWS = half4(TransformObjectToWorldDir(input.tangentOS.xyz), input.tangentOS.w);
                output.uv = TRANSFORM_TEX(input.uv, _AsphaltAlbedo);
                output.vertexSH = SampleSH(output.normalWS);
                return output;
            }

            half4 ForwardFrag(Varyings input) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

                half4 asphalt = SAMPLE_TEXTURE2D(_AsphaltAlbedo, sampler_AsphaltAlbedo, input.uv);
                half alpha = GetRoadAlpha(asphalt.a);
                half dither = GetScreenDither(input.positionCS.xy);
                half ditheredCutoff = saturate(_AlphaCutoff + (dither - 0.5h) * _DitherWidth);
                clip(alpha - ditheredCutoff);

                half3 normalTS = UnpackNormalScale(SAMPLE_TEXTURE2D(_AsphaltNormal, sampler_AsphaltNormal, input.uv), _NormalScale);
                half sign = input.tangentWS.w * GetOddNegativeScale();
                half3 bitangentWS = cross(input.normalWS, input.tangentWS.xyz) * sign;
                half3 normalWS = TransformTangentToWorld(normalTS, half3x3(input.tangentWS.xyz, bitangentWS, input.normalWS));
                normalWS = NormalizeNormalPerPixel(normalWS);

                float4 shadowCoord = TransformWorldToShadowCoord(input.positionWS);
                Light mainLight = GetMainLight(shadowCoord);
                half ndotl = saturate(dot(normalWS, mainLight.direction));
                half3 diffuse = input.vertexSH + mainLight.color * ndotl * mainLight.distanceAttenuation;

                // Alpha controls how much of the realtime main-light shadow
                // mask is applied. Zero leaves the transparent road unshadowed.
                half shadowAmount = (1.0h - mainLight.shadowAttenuation) * saturate(_RealtimeShadowColor.a);
                half3 realtimeShadowTint = lerp(half3(1.0h, 1.0h, 1.0h), _RealtimeShadowColor.rgb, shadowAmount);
                return half4(asphalt.rgb * diffuse * realtimeShadowTint, 1);
            }
            ENDHLSL
        }
    }

    FallBack Off
}
