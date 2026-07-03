Shader "PCG Bike/Road/Four Layer Vertex Color URP"
{
    Properties
    {
        _AsphaltTex ("Asphalt R", 2D) = "white" {}
        _GravelTex ("Gravel G", 2D) = "white" {}
        _MudTex ("Mud B", 2D) = "white" {}
        _DirtTex ("Dirt A", 2D) = "white" {}

        _AsphaltTint ("Asphalt Tint", Color) = (1, 1, 1, 1)
        _GravelTint ("Gravel Tint", Color) = (1, 1, 1, 1)
        _MudTint ("Mud Tint", Color) = (1, 1, 1, 1)
        _DirtTint ("Dirt Tint", Color) = (1, 1, 1, 1)

        _BlendNoiseTex ("Blend Noise RGBA", 2D) = "gray" {}
        _NoiseScale ("Noise Scale", Float) = 8
        _NoiseStrength ("Noise Strength", Range(0, 1)) = 0.25
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

            TEXTURE2D(_AsphaltTex);      SAMPLER(sampler_AsphaltTex);
            TEXTURE2D(_GravelTex);       SAMPLER(sampler_GravelTex);
            TEXTURE2D(_MudTex);          SAMPLER(sampler_MudTex);
            TEXTURE2D(_DirtTex);         SAMPLER(sampler_DirtTex);
            TEXTURE2D(_BlendNoiseTex);   SAMPLER(sampler_BlendNoiseTex);

            CBUFFER_START(UnityPerMaterial)
                float4 _AsphaltTex_ST;
                float4 _GravelTex_ST;
                float4 _MudTex_ST;
                float4 _DirtTex_ST;
                float4 _BlendNoiseTex_ST;
                half4 _AsphaltTint;
                half4 _GravelTint;
                half4 _MudTint;
                half4 _DirtTint;
                half _NoiseScale;
                half _NoiseStrength;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                half3 normalOS : NORMAL;
                float2 uv : TEXCOORD0;
                half4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                half3 normalWS : TEXCOORD0;
                float2 uv : TEXCOORD1;
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
                output.normalWS = normalInputs.normalWS;
                output.uv = input.uv;
                output.color = saturate(input.color);
                return output;
            }

            half4 NormalizeWeights(half4 weights)
            {
                weights = saturate(weights);
                half sumWeights = max(dot(weights, half4(1, 1, 1, 1)), half(0.0001));
                return weights / sumWeights;
            }

            half4 ApplyNoiseToTransition(half4 weights, float2 uv)
            {
                half dominant = max(max(weights.r, weights.g), max(weights.b, weights.a));
                half transitionMask = saturate((half(1.0) - dominant) * half(2.0));
                float2 noiseUV = uv * _NoiseScale;
                noiseUV = noiseUV * _BlendNoiseTex_ST.xy + _BlendNoiseTex_ST.zw;
                half4 noise = SAMPLE_TEXTURE2D(_BlendNoiseTex, sampler_BlendNoiseTex, noiseUV);
                half4 offset = (noise - half(0.5)) * _NoiseStrength * transitionMask;
                return NormalizeWeights(weights + offset);
            }

            half4 FragForward(Varyings input) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);

                half4 weights = ApplyNoiseToTransition(NormalizeWeights(input.color), input.uv);

                half3 asphalt = SAMPLE_TEXTURE2D(_AsphaltTex, sampler_AsphaltTex, TRANSFORM_TEX(input.uv, _AsphaltTex)).rgb * _AsphaltTint.rgb;
                half3 gravel = SAMPLE_TEXTURE2D(_GravelTex, sampler_GravelTex, TRANSFORM_TEX(input.uv, _GravelTex)).rgb * _GravelTint.rgb;
                half3 mud = SAMPLE_TEXTURE2D(_MudTex, sampler_MudTex, TRANSFORM_TEX(input.uv, _MudTex)).rgb * _MudTint.rgb;
                half3 dirt = SAMPLE_TEXTURE2D(_DirtTex, sampler_DirtTex, TRANSFORM_TEX(input.uv, _DirtTex)).rgb * _DirtTint.rgb;

                half3 albedo = asphalt * weights.r + gravel * weights.g + mud * weights.b + dirt * weights.a;

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
