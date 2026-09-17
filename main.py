# ==================== WEBVIEW APP CHAT API ROUTE ====================
@app.route('/api/chat', methods=['POST'])
def api_chat():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return Response("[Error: GEMINI_API_KEY environment variable is missing on server.]", mimetype='text/plain')
    
    client = genai.Client(api_key=api_key)

    # ပုံ (သို့မဟုတ်) ဖိုင်ပါလာခြင်း ရှိမရှိ စစ်ဆေးခြင်း
    if request.files:
        device_id = request.form.get("device_id")
        prompt = request.form.get("prompt", "")
        user_id = request.form.get("user_id", 0)
        image_file = request.files.get("image")
        
        file_data = None
        if image_file:
            image_bytes = image_file.read()
            file_data = types.Part.from_bytes(
                data=image_bytes,
                mime_type=image_file.content_type
            )
    else:
        data = request.json or {}
        device_id = data.get("device_id")
        prompt = data.get("prompt", "")
        user_id = data.get("user_id", 0)
        file_data = None

    # အသုံးပြုသူ အမျိုးအစား ခွဲခြားခြင်း (Owner, VIP, Free)
    try:
        user_id_int = int(user_id) if user_id else 0
    except:
        user_id_int = 0

    is_owner = (user_id_int == OWNER_ID or device_id == "055f419d68dab9df")
    user_is_vip = is_vip(device_id)

    # Free user များ Code တောင်းခြင်း ရှိမရှိ စစ်ဆေးရန် Keywords များ
    code_keywords = ["code", "python", "html", "javascript", "script", "program", "function", "source", "ကုဒ်", "ရေးပေး", "ရေးပြ"]
    is_asking_for_code = any(keyword in prompt.lower() for keyword in code_keywords)

    if not is_owner and not user_is_vip and is_asking_for_code:
        def restricted_generate():
            yield "❌ **Access Denied:** Free user များအနေဖြင့် AI ဆီမှ Code များကို တောင်းခံခွင့်မရှိပါ။ Code များ ရေးခိုင်းနိုင်ရန် VIP အဆင့်သို့ Upgrade ပြုလုပ်ပါ။"
        return Response(stream_with_context(restricted_generate()), mimetype='text/plain')

    # ==================== AI IMAGE GENERATION HANDLING (Nano Banana Models) ====================
    image_keywords = ["generate", "create", "draw", "painting", "photo", "image", "img", "ပုံဖန်တီး", "ပုံဆွဲ", "ပုံထုတ်", "ပုံ"]
    is_asking_for_image = any(keyword in prompt.lower() for keyword in image_keywords)

    if is_asking_for_image and not file_data:
        def generate_image_response():
            try:
                # Owner နှင့် VIP များအတွက် nano-banana-2 ကိုသုံးမည်၊ Free များအတွက် nano-banana-2-lite ကိုသုံးမည်
                img_model_name = 'nano-banana-2' if (is_owner or user_is_vip) else 'nano-banana-2-lite'

                result = client.models.generate_images(
                    model=img_model_name,
                    prompt=prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        output_mime_type="image/jpeg",
                        aspect_ratio="1:1"
                    )
                )
                for generated_image in result.generated_images:
                    import base64
                    img_base64 = base64.b64encode(generated_image.image.image_bytes).decode('utf-8')
                    yield f"![Generated Image](data:image/jpeg;base64,{img_base64})\n\n✨ **Prompt:** {prompt} (Model: {img_model_name})"
            except Exception as e:
                yield f"\n[Image Generation Error: {str(e)}]"
        return Response(stream_with_context(generate_image_response()), mimetype='text/plain')

    # Model နှင့် System Instruction သတ်မှတ်ခြင်း (စကားပြောရန်အတွက်)
    if is_owner:
        model_name = 'gemini-3.5-flash-lite'
        system_instruction = "You are Xinon AI, an elite, highly respectful personal assistant to your Creator and Boss..."
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
    elif user_is_vip:
        model_name = 'gemini-3.5-flash-lite'
        system_instruction = "You are Xinon AI, a premium and advanced assistant for VIP users, providing deep analytical, highly accurate, and professional responses..."
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
    else:
        model_name = 'gemini-3.1-flash-lite'
        system_instruction = "You are Xinon AI, a standard helpful assistant..."
        safety_settings = []

    contents = [prompt] if prompt else []
    if file_data:
        contents.append(file_data)

    def generate():
        try:
            response = client.models.generate_content_stream(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    safety_settings=safety_settings if safety_settings else None,
                )
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"\n[Error: {str(e)}]"

    return Response(stream_with_context(generate()), mimetype='text/plain')
