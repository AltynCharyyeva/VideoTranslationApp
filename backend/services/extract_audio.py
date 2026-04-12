import subprocess
import os


def extract_audio(video_path: str, output_dir: str) -> str:

    filename = os.path.basename(video_path).split(".")[0]
    audio_path = os.path.join(output_dir, f"{filename}.wav")
    
    command = [
        "ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1", audio_path, "-y"
    ]
    subprocess.run(command, check=True)
    print("Audio extracted\n")
    return audio_path