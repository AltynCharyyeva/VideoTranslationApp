import subprocess
import os


def extract_audio(video_path: str, output_dir: str) -> str:

    filename = os.path.basename(video_path).split(".")[0]
    audio_path = os.path.join(output_dir, f"{filename}.wav")
    
    command = [
        "ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1", audio_path, "-y"
    ]
    # - vn          -> Video None       -> tells ffmpeg to process only audio
    # - acodec      -> Audio Codec      -> defines the coder to use
    # - pcm_s16le   -> The Formant      -> Uncompressed 16-bit Signed Integer, Little Endian. Creates raw .wav file
    # - ar          -> Audio Rate       -> Sets the sampling rate
    # - 16000                              Sets the frequency
    # - ac          -> Audio Channels   -> Sets the number of output channels
    # - 1           -> Mono             -> Converts the audio into a single channel
    # - y           -> Yes              -> Overwrites the output file
    subprocess.run(command, check=True)
    print("Audio extracted\n")
    return audio_path