import json
import os
import subprocess

def run_ffmpeg_command(command):
    try:
        subprocess.run(command, check=True, shell=True)
        print(f"Command executed successfully: {command}")
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {command}")
        print(f"Error: {e}")
        exit(1)

def generate_video(config, template_video_path, chroma_video_path, surah_name_image_path, qari_name_image_path, output_path, preview_mode=False):
    output_resolution = config['output_resolution']
    output_codec = config['output_codec']
    output_format = config['output_format']

    # FFmpeg complex filter graph
    filters = []
    inputs = [
        f"-i \"{template_video_path}\"",
        f"-i \"{chroma_video_path}\""
    ]

    # Overlay chroma video
    chroma_x = config['chroma_settings']['position_x']
    chroma_y = config['chroma_settings']['position_y']
    chroma_scale = config['chroma_settings']['scale']
    filters.append(f"[1:v]scale=iw*{chroma_scale}:-1[chroma_scaled];[0:v][chroma_scaled]overlay={chroma_x}:{chroma_y}:format=auto:shortest=1[temp_video]")

    # Add surah name image if provided
    if surah_name_image_path and os.path.exists(surah_name_image_path):
        inputs.append(f"-i \"{surah_name_image_path}\" ")
        surah_x = config['surah_name_settings']['position_x']
        surah_y = config['surah_name_settings']['position_y']
        surah_scale = config['surah_name_settings']['scale']
        filters.append(f"[2:v]scale=iw*{surah_scale}:-1[surah_scaled];[temp_video][surah_scaled]overlay={surah_x}:{surah_y}:format=auto[temp_video2]")
        current_video_stream = "temp_video2"
    else:
        current_video_stream = "temp_video"

    # Add qari name image if provided
    if qari_name_image_path and os.path.exists(qari_name_image_path):
        inputs.append(f"-i \"{qari_name_image_path}\" ")
        qari_x = config['qari_name_settings']['position_x']
        qari_y = config['qari_name_settings']['position_y']
        qari_scale = config['qari_name_settings']['scale']
        # Adjust input index based on whether surah name was added
        qari_input_index = 3 if surah_name_image_path and os.path.exists(surah_name_image_path) else 2
        filters.append(f"[{qari_input_index}:v]scale=iw*{qari_scale}:-1[qari_scaled];[{current_video_stream}][qari_scaled]overlay={qari_x}:{qari_y}:format=auto[final_video]")
        current_video_stream = "final_video"
    else:
        if surah_name_image_path and os.path.exists(surah_name_image_path):
            current_video_stream = "temp_video2"
        else:
            current_video_stream = "temp_video"

    # Final output stream and audio handling
    final_filter = f"-map \"[{current_video_stream}]\" -map 1:a? -c:v {output_codec} -preset ultrafast -crf 23 -c:a aac -b:a 192k -vf \"format=yuv420p,scale={output_resolution}\""

    if preview_mode:
        # For preview, just output a single frame (image)
        command = f"ffmpeg {' '.join(inputs)} -filter_complex \"{';'.join(filters)}\" -frames:v 1 -y \"{output_path}\"
        print("Generating preview...")
    else:
        command = f"ffmpeg {' '.join(inputs)} -filter_complex \"{';'.join(filters)}\" {final_filter} -y \"{output_path}\"
        print(f"Generating video: {output_path}")

    run_ffmpeg_command(command)

def main():
    config_path = 'quran_video_producer/config.json'
    if not os.path.exists(config_path):
        print(f"Error: config.json not found at {config_path}")
        exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    template_video = config['template_video']
    template_video_path = os.path.join('quran_video_producer', template_video)
    if not os.path.exists(template_video_path):
        print(f"Error: Template video not found at {template_video_path}")
        exit(1)

    chromas_dir = 'quran_video_producer/input/chromas'
    surah_names_dir = 'quran_video_producer/input/surah_names'
    qari_names_dir = 'quran_video_producer/input/qari_names'
    output_dir = 'quran_video_producer/output'

    chroma_files = [f for f in os.listdir(chromas_dir) if f.endswith(('.mp4', '.mov'))]
    if not chroma_files:
        print(f"No chroma videos found in {chromas_dir}")
        exit(1)

    # --- Preview Mode ---
    print("\n--- PREVIEW MODE ---")
    first_chroma_file = chroma_files[0]
    chroma_video_path = os.path.join(chromas_dir, first_chroma_file)

    # Try to find corresponding surah name image
    surah_name_base = os.path.splitext(first_chroma_file)[0].split('_')[0] # Assuming format like '001_Fatiha.mp4'
    surah_name_image_path = None
    for ext in ['.png', '.jpg']:
        potential_path = os.path.join(surah_names_dir, f'{surah_name_base}{ext}')
        if os.path.exists(potential_path):
            surah_name_image_path = potential_path
            break

    # Assume qari name is constant for all videos for simplicity in preview
    qari_name_image_path = None
    qari_files = [f for f in os.listdir(qari_names_dir) if f.endswith(('.png', '.jpg'))]
    if qari_files:
        qari_name_image_path = os.path.join(qari_names_dir, qari_files[0])

    preview_output_path = os.path.join(output_dir, 'preview.png')
    generate_video(config, template_video_path, chroma_video_path, surah_name_image_path, qari_name_image_path, preview_output_path, preview_mode=True)
    print(f"Preview image generated at: {preview_output_path}")
    print("Please check 'preview.png' in the output folder. Adjust config.json if needed.")
    input("Press Enter to continue with full video generation, or Ctrl+C to exit and adjust config.json...")

    # --- Full Generation Mode ---
    print("\n--- FULL GENERATION MODE ---")
    for chroma_file in chroma_files:
        chroma_video_path = os.path.join(chromas_dir, chroma_file)
        output_filename = f"final_{os.path.splitext(chroma_file)[0]}.{output_format}"
        output_path = os.path.join(output_dir, output_filename)

        # Dynamic surah name image based on chroma file name
        surah_name_base = os.path.splitext(chroma_file)[0].split('_')[0] # Assuming format like '001_Fatiha.mp4'
        surah_name_image_path = None
        for ext in ['.png', '.jpg']:
            potential_path = os.path.join(surah_names_dir, f'{surah_name_base}{ext}')
            if os.path.exists(potential_path):
                surah_name_image_path = potential_path
                break

        # Use the first qari name image found for all videos (or you can make this dynamic too)
        qari_name_image_path = None
        if qari_files:
            qari_name_image_path = os.path.join(qari_names_dir, qari_files[0])

        generate_video(config, template_video_path, chroma_video_path, surah_name_image_path, qari_name_image_path, output_path)

    print("\nAll videos generated successfully!")

if __name__ == "__main__":
    main()
