import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import textwrap
from gtts import gTTS
import os
import asyncio
from moviepy.editor import ImageClip, AudioFileClip, VideoFileClip, concatenate_videoclips
from typing import List, Optional, Tuple # Added typing imports

# --- MCP Setup ---
# Try importing the real FastMCP, fall back to a mock for demonstration
try:
    from mcp.server.fastmcp import FastMCP
    print("Using installed FastMCP")
except ImportError:
    print("Warning: FastMCP not found. Using MockMCP for demonstration.")
    # ---- Mock FastMCP for demonstration if library isn't installed ----
    class MockMCP:
        def __init__(self, name: str):
            self.name = name
            self._tools = {}
            print(f"MCP Service '{self.name}' initialized (Mock).")

        def tool(self):
            def decorator(func):
                self._tools[func.__name__] = func
                print(f"Tool '{func.__name__}' registered (Mock).")
                # Basic signature extraction for mock run
                import inspect
                sig = inspect.signature(func)
                print(f"  Signature: {func.__name__}{sig}")
                return func
            return decorator

        def run(self, transport: str = 'stdio'):
            print(f"\nMCP Service '{self.name}' starting run loop (transport: {transport}) (Mock).")
            print("Registered tools:", list(self._tools.keys()))
            print("--- Mock Server Ready ---")
            print("To test with MockMCP, manually call the tool function like:")
            print("async def main():")
            print("  result = await create_mcq_video(csv_file_path='your_data.csv')")
            print("  print(result)")
            print("asyncio.run(main())")
            # In a real server, this would listen via stdio/http etc.
            # Keep running indefinitely for a mock server unless interrupted
            try:
                loop = asyncio.get_event_loop()
                loop.run_forever()
            except KeyboardInterrupt:
                print("\nMock server shutdown.")
            finally:
                loop.close()

# Initialize MCP Server
mcp = FastMCP("mcq_video_generator") # Or MockMCP("mcq_video_generator")

# --- Constants ---
DEFAULT_IMAGE_WIDTH = 1920
DEFAULT_IMAGE_HEIGHT = 1080
DEFAULT_BACKGROUND_COLOR = (0, 127, 215) # RGB tuple
DEFAULT_FONT_COLOR = (255, 255, 255) # RGB tuple
DEFAULT_FONT_SIZE = 70 # Reduced slightly for potentially longer English text
DEFAULT_LINE_SPACING = 10
DEFAULT_MARGIN = 80
DEFAULT_TEXT_WRAP_WIDTH = 45 # Adjusted for font size/resolution
DEFAULT_FPS = 24
DEFAULT_LANGUAGE = 'en' # Default language for gTTS
DEFAULT_FONT_PATH = "HindVadodara-Light.ttf" # <<< IMPORTANT: Ensure this font exists or provide path

# --- Helper Functions ---

def create_image_for_mcq(
    data_row: List[str],
    image_path: str,
    width: int,
    height: int,
    bg_color: Tuple[int, int, int],
    font_color: Tuple[int, int, int],
    font_size: int,
    font_path: str,
    line_spacing: int,
    margin: int,
    wrap_width: int
) -> str:
    """Generates a single image for an MCQ item and returns the text content."""
    try:
        image = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(image)
        # Ensure font exists
        if not os.path.exists(font_path):
             raise FileNotFoundError(f"Font file not found at: {font_path}")
        font = ImageFont.truetype(font_path, font_size)
        y_position = margin
        text_content = ""

        for text in data_row:
            if not isinstance(text, str): # Handle potential non-string data (e.g., NaN from pandas)
                 text = str(text)
            # Basic cleanup: remove excessive whitespace
            text = ' '.join(text.split())
            if not text: # Skip empty strings after cleanup
                 continue

            wrapped_text = textwrap.fill(text, width=wrap_width)
            lines = wrapped_text.split('\n')

            for line in lines:
                # Calculate text width to potentially center or adjust later if needed
                # text_width, text_height = draw.textsize(line, font=font) # Deprecated
                try:
                    # Use textbbox for more accurate size calculation
                    bbox = draw.textbbox((margin, y_position), line, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1] # Approx height, font_size is often sufficient
                except AttributeError: # Fallback for older PIL/Pillow
                     text_width = draw.textlength(line, font=font)


                # Draw text - simple left alignment at margin
                draw.text((margin, y_position), line, font=font, fill=font_color)
                y_position += font_size + line_spacing # Move y down
                text_content += line + " " # Add space for better TTS separation

            y_position += line_spacing * 2 # Add extra spacing between original data elements

        image.save(image_path)
        return text_content.strip() # Return combined text for TTS

    except FileNotFoundError as e:
        raise e # Re-raise font not found error
    except Exception as e:
        raise RuntimeError(f"Error creating image {image_path}: {e}")

def create_audio_for_mcq(text: str, audio_path: str, lang: str) -> None:
    """Generates a single MP3 audio file for the given text using gTTS."""
    try:
        tts = gTTS(text=text, lang=lang)
        tts.save(audio_path)
    except Exception as e:
        raise RuntimeError(f"Error creating audio {audio_path} with gTTS: {e}")

def create_video_clip(image_path: str, audio_path: str, video_path: str, fps: int) -> float:
    """Combines an image and audio into a video clip."""
    try:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        audio_clip = AudioFileClip(audio_path)
        audio_duration = audio_clip.duration

        if audio_duration is None or audio_duration <= 0:
             print(f"Warning: Audio duration for {audio_path} is invalid ({audio_duration}). Using default 1s.")
             audio_duration = 1.0 # Avoid zero duration clips

        image_clip = ImageClip(image_path)
        video_clip = image_clip.set_audio(audio_clip)
        video_clip = video_clip.set_duration(audio_duration)
        video_clip = video_clip.set_fps(fps)

        # Write the video file
        video_clip.write_videofile(video_path, codec="libx264", audio_codec="aac", logger=None) # Suppress verbose output

        # Close clips to release resources
        audio_clip.close()
        image_clip.close()
        video_clip.close()

        return audio_duration # Return duration for potential use

    except Exception as e:
        # Clean up potentially open clips on error
        if 'audio_clip' in locals() and audio_clip: audio_clip.close()
        if 'image_clip' in locals() and image_clip: image_clip.close()
        if 'video_clip' in locals() and video_clip: video_clip.close()
        raise RuntimeError(f"Error creating video clip {video_path}: {e}")

def concatenate_videos(video_paths: List[str], final_video_path: str) -> None:
    """Concatenates a list of video files into one."""
    if not video_paths:
        raise ValueError("No video paths provided for concatenation.")

    clips = []
    try:
        for path in video_paths:
            if not os.path.exists(path):
                 raise FileNotFoundError(f"Video clip not found for concatenation: {path}")
            clips.append(VideoFileClip(path))

        final_clip = concatenate_videoclips(clips, method="compose") # Use 'compose' if clips have different sizes/fps potentially
        final_clip.write_videofile(final_video_path, codec="libx264", audio_codec="aac", logger=None) # Suppress verbose output

    except Exception as e:
        raise RuntimeError(f"Error concatenating videos to {final_video_path}: {e}")
    finally:
        # Ensure all clips are closed
        for clip in clips:
            clip.close()
        if 'final_clip' in locals() and final_clip:
            final_clip.close()


# --- MCP Tool Definition ---

@mcp.tool()
async def create_mcq_video(
    csv_file_path: str,
    output_filename: str = "Gyan_Dariyo_final_video.mp4",
    language: str = DEFAULT_LANGUAGE,
    font_path: str = DEFAULT_FONT_PATH,
    font_size: int = DEFAULT_FONT_SIZE,
    img_width: int = DEFAULT_IMAGE_WIDTH,
    img_height: int = DEFAULT_IMAGE_HEIGHT,
    bg_color_rgb: Tuple[int, int, int] = DEFAULT_BACKGROUND_COLOR,
    font_color_rgb: Tuple[int, int, int] = DEFAULT_FONT_COLOR
) -> str:
    """
    Generates a video from Multiple Choice Questions stored in a CSV file.

    Each row in the CSV should represent one question slide. Columns typically
    contain the question, options (A, B, C, D), and the answer.
    The tool creates an image and audio for each row, combines them into
    a video clip, and finally concatenates all clips into a single video file.

    Args:
        csv_file_path: Path to the input CSV file containing MCQ data.
        output_filename: Desired filename for the final output video (e.g., 'my_quiz.mp4').
                         Intermediate files will be stored in a directory based on this name.
        language: Language code for Text-to-Speech generation (e.g., 'en', 'gu'). Defaults to 'en'.
        font_path: Path to the .ttf font file to use for text rendering.
                   Defaults to 'HindVadodara-Light.ttf'. Ensure this file exists.
        font_size: Font size for the text on the images. Defaults to 70.
        img_width: Width of the output video/images in pixels. Defaults to 1920.
        img_height: Height of the output video/images in pixels. Defaults to 1080.
        bg_color_rgb: Background color as an RGB tuple (R, G, B). Defaults to (0, 127, 215).
        font_color_rgb: Font color as an RGB tuple (R, G, B). Defaults to (255, 255, 255).

    Returns:
        str: The absolute path to the generated final video file on success,
             or an error message string on failure.
    """
    print(f"Received request to create MCQ video from: {csv_file_path}")
    print(f"Output will be: {output_filename}")

    try:
        # --- 1. Input Validation and Setup ---
        if not os.path.exists(csv_file_path):
            return f"Error: Input CSV file not found at '{csv_file_path}'"
        if not os.path.exists(font_path):
             return f"Error: Font file not found at '{font_path}'. Please provide a valid path."

        # Create output directory based on the output filename
        output_base_name = os.path.splitext(output_filename)[0]
        output_dir = os.path.abspath(f"./{output_base_name}_output") # Place in CWD
        os.makedirs(output_dir, exist_ok=True)
        print(f"Using output directory: {output_dir}")

        final_video_full_path = os.path.join(output_dir, output_filename)

        # --- 2. Load Data ---
        try:
            data_frame = pd.read_csv(csv_file_path, keep_default_na=False, dtype=str) # Read all as string, keep blanks
            # Handle potential empty rows or header issues if needed
            data_frame = data_frame.dropna(how='all') # Drop rows where *all* cells are NaN/empty
            if data_frame.empty:
                 return f"Error: CSV file '{csv_file_path}' seems to be empty or contains no valid data rows."
            data_list = data_frame.values.tolist()
            print(f"Loaded {len(data_list)} MCQ items from CSV.")
        except pd.errors.EmptyDataError:
             return f"Error: CSV file '{csv_file_path}' is empty."
        except Exception as e:
            return f"Error reading CSV file '{csv_file_path}': {e}"

        # --- 3. Process Each MCQ Item ---
        individual_video_paths = []
        total_duration = 0

        for idx, data_row in enumerate(data_list):
            item_num = idx + 1
            print(f"Processing item {item_num}/{len(data_list)}...")

            # Define paths for intermediate files for this item
            image_file = os.path.join(output_dir, f"mcq_img_{item_num}.png")
            audio_file = os.path.join(output_dir, f"mcq_audio_{item_num}.mp3")
            video_file = os.path.join(output_dir, f"mcq_video_{item_num}.mp4")

            try:
                # a. Generate Image and get text
                print(f"  Generating image: {image_file}")
                # Run synchronous image creation in executor for better async behavior
                text_for_speech = await asyncio.to_thread(
                    create_image_for_mcq,
                    data_row, image_file, img_width, img_height, bg_color_rgb,
                    font_color_rgb, font_size, font_path, DEFAULT_LINE_SPACING,
                    DEFAULT_MARGIN, DEFAULT_TEXT_WRAP_WIDTH
                )

                if not text_for_speech:
                    print(f"  Warning: No text content generated for item {item_num}. Skipping audio/video.")
                    continue # Skip if no text content

                # b. Generate Audio
                print(f"  Generating audio: {audio_file} (lang={language})")
                # Run synchronous gTTS call in executor
                await asyncio.to_thread(create_audio_for_mcq, text_for_speech, audio_file, language)

                # c. Generate Individual Video Clip
                print(f"  Generating video clip: {video_file}")
                # Run synchronous moviepy call in executor
                clip_duration = await asyncio.to_thread(
                    create_video_clip, image_file, audio_file, video_file, DEFAULT_FPS
                )
                individual_video_paths.append(video_file)
                total_duration += clip_duration
                print(f"  Item {item_num} processed. Clip duration: {clip_duration:.2f}s")

            except Exception as e:
                # Log error for the specific item but try to continue with others
                print(f"  Error processing item {item_num}: {e}. Skipping this item.")
                # Optionally: Clean up partial files for this item
                if os.path.exists(image_file): os.remove(image_file)
                if os.path.exists(audio_file): os.remove(audio_file)
                if os.path.exists(video_file): os.remove(video_file)
                continue # Skip to next item

        # --- 4. Concatenate Video Clips ---
        if not individual_video_paths:
            return "Error: No individual video clips were successfully generated. Final video cannot be created."

        print(f"\nConcatenating {len(individual_video_paths)} video clips into {final_video_full_path}...")
        print(f"Estimated total duration: {total_duration:.2f}s")
        try:
             # Run synchronous moviepy call in executor
             await asyncio.to_thread(concatenate_videos, individual_video_paths, final_video_full_path)
             print("Concatenation complete.")
        except Exception as e:
            return f"Error during final video concatenation: {e}"

        # --- 5. Cleanup (Optional) ---
        # Consider adding an option to keep or delete intermediate files
        # For now, we keep them in the output directory.
        # Example cleanup:
        # print("Cleaning up intermediate files...")
        # for path in individual_video_paths:
        #     img_path = path.replace(".mp4", ".png").replace("video", "img")
        #     aud_path = path.replace(".mp4", ".mp3").replace("video", "audio")
        #     if os.path.exists(path): os.remove(path)
        #     if os.path.exists(img_path): os.remove(img_path)
        #     if os.path.exists(aud_path): os.remove(aud_path)

        # --- 6. Return Result ---
        print(f"Successfully generated final video: {final_video_full_path}")
        return final_video_full_path

    except Exception as e:
        # Catch any unexpected errors during the process
        import traceback
        print(f"An unexpected error occurred: {e}")
        traceback.print_exc()
        return f"Error: An unexpected error occurred during video generation: {e}"

# --- Main Execution Block ---
if __name__ == "__main__":
    print("Starting MCQ Video Generator MCP Server...")
    # Example on how to test with MockMCP (if used)
    async def run_mock_test():
        if isinstance(mcp, MockMCP):
             print("\n--- Running Mock Test ---")
             # Create a dummy CSV for testing
             dummy_csv_path = "mock_mcq_data.csv"
             dummy_data = {
                  'Question': ["Q1: What is 1+1?", "Q2: Capital of France?"],
                  'A': ["A. 1", "A. London"],
                  'B': ["B. 2", "B. Berlin"],
                  'C': ["C. 3", "C. Paris"],
                  'D': ["D. 4", "D. Rome"],
                  'Answer': ["Ans: B. 2", "Ans: C. Paris"]
             }
             pd.DataFrame(dummy_data).to_csv(dummy_csv_path, index=False)
             print(f"Created dummy CSV: {dummy_csv_path}")

             # Check if default font exists, otherwise skip mock call
             if not os.path.exists(DEFAULT_FONT_PATH):
                  print(f"SKIPPING MOCK CALL: Default font '{DEFAULT_FONT_PATH}' not found.")
                  print("Place the font file or provide a valid 'font_path' argument.")
             else:
                  print(f"Attempting mock call with font: {DEFAULT_FONT_PATH}")
                  result = await create_mcq_video(csv_file_path=dummy_csv_path, output_filename="mock_test_video.mp4")
                  print(f"\nMock Test Result:\n{result}")
             print("--- Mock Test End ---")

    # If using MockMCP, run the test, otherwise just start the server run loop
    if isinstance(mcp, MockMCP):
         asyncio.run(run_mock_test())
         # Keep the mock server running after the test if needed
         # print("\nMock server running. Press Ctrl+C to stop.")
         # try:
         #     asyncio.get_event_loop().run_forever()
         # except KeyboardInterrupt:
         #     print("\nMock server stopped.")
         # finally:
         #      asyncio.get_event_loop().close()
    else:
        # Start the real MCP server loop (blocking)
        mcp.run(transport='stdio')

    print("MCP Server finished.")