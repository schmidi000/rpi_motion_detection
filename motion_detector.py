#!/usr/bin/python3
import argparse
import datetime
import logging
import os
import signal
import sys

import numpy as np
from picamera2 import Picamera2, Preview
from picamera2.encoders import H264Encoder
from picamera2.outputs import CircularOutput

from service.google_drive_service import GoogleDriveService

# setLevel(logging.WARNING) seems to have no impact
logging.getLogger("picamera2").disabled = True
logging.getLogger("google").setLevel(logging.WARNING)


def command_line_handler(signum, frame):
    res = input("Ctrl-c was pressed. Do you really want to exit? y/n ")
    if res == 'y':
        motion_detector.stop()


def parse_command_line_arguments():
    parser = argparse.ArgumentParser(
        description='Motion detection for Raspberry Pi Camera Module 2 with optional Google Drive service.')
    parser.add_argument('--preview', help='enables the preview window', required=False, action='store_true')
    parser.add_argument('--preview-x', type=int, default=100,
                        help='preview window location x-axis')
    parser.add_argument('--preview-y', type=int, default=200,
                        help='preview window location y-axis')
    parser.add_argument('--preview-width', type=int, default=800,
                        help='preview window width')
    parser.add_argument('--preview-height', type=int, default=600,
                        help='preview window height')
    parser.add_argument('--zoom', type=float, default=1.0,
                        help='zoom factor (0.5 is half of the resolution and therefore the zoom is x 2)',
                        required=False)
    parser.add_argument('--width', type=int, default=1280, help='camera resolution width for high resolution',
                        required=False)
    parser.add_argument('--height', type=int, default=720, help='camera resolution height for high resolution',
                        required=False)
    parser.add_argument('--lores-width', type=int, default=320, help='camera resolution width for low resolution',
                        required=False)
    parser.add_argument('--lores-height', type=int, default=240, help='camera resolution height for low resolution',
                        required=False)
    parser.add_argument('--drive-upload', help='enables service of videos to Google Drive', action='store_true')
    parser.add_argument('--min-pixel-diff', type=float, default=7.2,
                        help='minimum number of pixel changes to detect motion (determined with numpy by calculating the mean of the squared pixel difference between two frames)',
                        required=False)
    parser.add_argument('--capture-lores', help='enables capture of lores buffer', action='store_true')
    parser.add_argument('--recording-dir', default='./recordings/', help='directory to store recordings',
                        required=False)
    parser.add_argument('--drive-folder', default='./motion/', help='directory to store recordings',
                        required=False)
    parser.add_argument('--delete-local-recordings-after-upload',
                        help='delete local recordings after Google Drive service',
                        required=False, action='store_true')
    parser.add_argument('--delete-recordings-after-seconds', type=int, default=0,
                        help='delete online recordings after X seconds')
    parser.add_argument('--token-path', type=str, default='./',
                        help='path to token.json')
    parser.add_argument('--credentials-path', type=str, default='./',
                        help='path to credentials.json')
    parser.add_argument('--max-recording-length-seconds', type=int, default=0,
                        help='limit recording length to seconds')

    return parser.parse_args()


class MotionDetector:
    """This class contains the main logic for motion detection."""
    __MAX_TIME_SINCE_LAST_MOTION_DETECTION_SECONDS = 5.0

    def __init__(self, args: argparse.Namespace):
        """MotionDetector

        :param args: command line arguments
        """
        self.__picam2 = None
        self.__encoder = None
        self.__encoding = False
        self.__start_time_of_last_recording = None
        self.__time_of_last_motion_detection = None

        self.__zoom_factor = args.zoom
        self.__lores_width = args.lores_width
        self.__lores_height = args.lores_height
        self.__width = args.width
        self.__height = args.height
        self.__min_pixel_diff = args.min_pixel_diff
        self.__capture_lores = args.capture_lores
        self.__google_drive_service = GoogleDriveService(token_path=args.token_path,
                                                         credentials_path=args.credentials_path) if args.drive_upload else None
        self.__recording_dir = args.recording_dir
        self.__delete_local_recordings_after_upload = args.delete_local_recordings_after_upload
        self.__delete_recordings_after_seconds = args.delete_recordings_after_seconds
        self.__preview_x = args.preview_x
        self.__preview_y = args.preview_y
        self.__preview_width = args.preview_width
        self.__preview_height = args.preview_height
        self.__max_recording_length_seconds = args.max_recording_length_seconds

        self.__set_up_camera(args.preview)

    def start(self):
        """
        Starts the camera and runs the loop.
        """
        self.__picam2.start()
        self.__picam2.start_encoder()

        self.__set_zoom_factor()

        self.__loop()

    def __loop(self):
        """
        Runs the actual motion detection loop that, optionally, triggers the Google Drive service.
        """
        w, h = self.__lsize
        previous_frame = None

        while True:
            current_frame = self.__picam2.capture_buffer("lores" if self.__capture_lores else "main")
            current_frame = current_frame[:w * h].reshape(h, w)
            if previous_frame is not None:
                mse = np.square(np.subtract(current_frame, previous_frame)).mean()
                if mse > self.__min_pixel_diff and not self.__is_max_recording_length_exceeded():
                    if not self.__encoding:
                        self.__start_time_of_last_recording = datetime.datetime.now()
                        logging.info(f"start recording of new recording: {self.__start_time_of_last_recording}")
                        self.__start_recording()
                    self.__time_of_last_motion_detection = datetime.datetime.now()
                elif self.__is_max_recording_length_exceeded():
                    logging.info(
                        f"max recording time exceeded after {(datetime.datetime.now() - self.__start_time_of_last_recording).total_seconds()} seconds")
                    self.__write_recording_to_file()
                else:
                    if self.__is_max_time_since_last_motion_detection_exceeded():
                        logging.info("diff between time now and last motion detection")
                        self.__write_recording_to_file()
            previous_frame = current_frame

    def __is_max_recording_length_exceeded(self):
        return self.__max_recording_length_seconds > 0 and self.__start_time_of_last_recording is not None and (
                (
                            datetime.datetime.now() - self.__start_time_of_last_recording).total_seconds() >= self.__max_recording_length_seconds
        )

    def __is_max_time_since_last_motion_detection_exceeded(self):
        return self.__encoding and self.__time_of_last_motion_detection is not None and \
               ((datetime.datetime.now() - self.__time_of_last_motion_detection).total_seconds() > self.__MAX_TIME_SINCE_LAST_MOTION_DETECTION_SECONDS)

    def __start_recording(self):
        self.__encoder.output.fileoutput = self.__get_recording_file_path()
        self.__encoder.output.start()
        self.__encoding = True

    def __write_recording_to_file(self):
        file_path = self.__get_recording_file_path()
        self.__encoder.output.stop()
        _, file_name = os.path.split(file_path)
        self.__upload_file(file_path=file_path, file_name=file_name)
        self.__encoding = False
        self.__start_time_of_last_recording = None

    def __get_recording_file_path(self):
        return f"{self.__recording_dir}{self.__start_time_of_last_recording.isoformat()}.h264"

    def __set_up_camera(self, enable_preview):
        """
        Configures the camera, preview window and encoder.

        :param enable_preview: enables preview window
        """
        self.__lsize = (self.__lores_width, self.__lores_height)
        self.__picam2 = Picamera2()
        video_config = self.__picam2.create_video_configuration(
            main={"size": (self.__width, self.__height), "format": "YUV420"},
            lores={"size": self.__lsize, "format": "YUV420"})
        self.__picam2.configure(video_config)

        if enable_preview:
            self.__picam2.start_preview(Preview.QTGL, x=self.__preview_x, y=self.__preview_y,
                                        width=self.__preview_width, height=self.__preview_height)

        self.__encoder = H264Encoder(1000000, repeat=True)
        self.__encoder.output = CircularOutput()
        self.__picam2.encoder = self.__encoder

    def __set_zoom_factor(self):
        """
        Sets the zoom factor of the camera.
        """
        size = self.__picam2.capture_metadata()['ScalerCrop'][2:]
        self.__picam2.capture_metadata()
        size = [int(s * self.__zoom_factor) for s in size]
        offset = [(r - s) // 2 for r, s in zip(self.__picam2.sensor_resolution, size)]
        self.__picam2.set_controls({"ScalerCrop": offset + size})

    def __delete_recording(self, file_path):
        """
        Deletes video, if the appropriate command line argument is supplied.
        :param file_path: file to delete
        """
        if self.__delete_local_recordings_after_upload:
            logging.info(f"Deleting local recording {file_path}")
            os.remove(file_path)

    def __delete_old_online_recordings(self):
        """
        Deletes all online recordings that are older than __delete_recordings_after_seconds.
        :return:
        """
        if self.__delete_recordings_after_seconds > 0:
            delete_before_date = datetime.datetime.now() - datetime.timedelta(
                seconds=self.__delete_recordings_after_seconds)
            self.__google_drive_service.delete_all_videos_older_than(delete_before_date)

    def __upload_file(self, file_path, file_name):
        """
        Uploads a video to Google Drive, if the appropriate command line argument is supplied.
        :param file_path:
        :param file_name:
        :return:
        """
        if self.__google_drive_service:
            self.__google_drive_service.upload_video(file_path=file_path, file_name=file_name)
            self.__delete_recording(file_path)
            self.__delete_old_online_recordings()

    def stop(self):
        """
        Stops the encoder and exits the application.
        """
        self.__picam2.stop_encoder()
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    command_line_arguments = parse_command_line_arguments()
    motion_detector = MotionDetector(command_line_arguments)
    signal.signal(signal.SIGINT, command_line_handler)
    motion_detector.start()
