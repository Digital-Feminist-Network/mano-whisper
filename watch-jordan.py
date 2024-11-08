import logging
import os
import subprocess
import threading
import time
from collections import deque

import psutil
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logging.basicConfig(
    filename="watch-jordan.log", level=logging.INFO, format="%(asctime)s - %(message)s"
)

# Constants.
output_dir = "/mnt/vol1/data_sets/digfem/podcast-analysis/media/The Jordan B. Peterson Podcast/vtt"
watch_dir = "/mnt/vol1/data_sets/digfem/podcast-analysis/media/The Jordan B. Peterson Podcast/mp3"

queue_file = "jordan-queue.txt"

QUEUE = deque()
PROCESSED_FILES = set()
LOCK = threading.Lock()
PROCESSING = False
PROCESS_DELAY = 0.5


# Load existing queue from file.
def load_queue():
    if os.path.exists(queue_file):
        with open(queue_file, "r") as f:
            for line in f:
                PROCESSED_FILES.add(line.strip())


def save_queue():
    with open(queue_file, "w") as f:
        for file in PROCESSED_FILES:
            f.write(f"{file}\n")


def check_whisper_running():
    """Check if the whisper process is currently running."""
    for proc in psutil.process_iter(["name"]):
        if proc.info["name"] == "whisper":
            return True
    return False


class FileEventHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        filename = os.path.basename(event.src_path)
        if filename.endswith(".mp3"):
            with LOCK:
                if filename not in PROCESSED_FILES and filename not in QUEUE:
                    logging.info(f"Detected new file event - {filename}")
                    QUEUE.append(filename)
                    if not PROCESSING:
                        threading.Thread(target=self.process_queue).start()

    def process_queue(self):
        global PROCESSING
        PROCESSING = True
        # Allow time for additional events to be captured.
        time.sleep(PROCESS_DELAY)
        while QUEUE:
            with LOCK:
                file_to_process = QUEUE.popleft()

            if check_whisper_running():
                logging.info("Whisper process is already running. Skipping processing.")
                QUEUE.appendleft(file_to_process)
                # Re-add to the queue for later processing.
                break

            logging.info(f"Processing file: {file_to_process}")
            command = f'/home/nruest/.pyenv/shims/whisper --threads 11 --model turbo --fp16 False --language en --output_format vtt --output_dir "{output_dir}" "{watch_dir}/{file_to_process}"'

            try:
                subprocess.run(command, shell=True, check=True)
                logging.info(f"Processing completed for {file_to_process}.")
                # Mark processed.
                PROCESSED_FILES.add(file_to_process)
            except subprocess.CalledProcessError as e:
                logging.error(f"Error processing file {file_to_process}: {e}")

            save_queue()

        PROCESSING = False


if __name__ == "__main__":
    load_queue()
    event_handler = FileEventHandler()
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
