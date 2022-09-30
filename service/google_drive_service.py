#!/usr/bin/python3
from __future__ import print_function

import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


class GoogleDriveService:
    _SCOPES = ['https://www.googleapis.com/auth/drive.file']

    def __init__(self, token_path="./token.json", credentials_path="./credentials.json"):
        self.__token_path = token_path
        self.__credentials_path = credentials_path
        self.__credentials = None
        self.__client = None
        self.__sign_in()
        self.__create_client()

    def __sign_in(self):
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists(self.__token_path):
            self.__credentials = Credentials.from_authorized_user_file(self.__token_path, self._SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not self.__credentials or not self.__credentials.valid:
            if self.__credentials and self.__credentials.expired and self.__credentials.refresh_token:
                self.__credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.__credentials_path, self._SCOPES)
                self.__credentials = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(self.__token_path, "w") as token:
                token.write(self.__credentials.to_json())

    def __create_client(self):
        self.__client = build("drive", "v3", credentials=self.__credentials)

    def __get_folder_id(self, google_drive_folder):
        """
        Creates the Google Drive folder if it does not already exist.
        If the folder exists, the ID is returned immediately.
        :param google_drive_folder: name of the Google Drive folder
        :return: id of the Google Drive folder
        """
        folders = self.__client.files().list(
            q=f"name='{google_drive_folder}' and mimeType='application/vnd.google-apps.folder' and trashed=false").execute()

        if len(folders.get("files")) == 1:
            return folders.get("files")[0].get("id")
        else:
            raise Exception(f"Folder with name {google_drive_folder} not found!")

    def __get_or_create_folder(self, google_drive_folder):
        """
        Creates the Google Drive folder if it does not already exist.
        If the folder exists, the ID is returned immediately.
        :param google_drive_folder: name of the Google Drive folder
        :return: id of the Google Drive folder
        """
        folders = self.__client.files().list(
            q=f"name='{google_drive_folder}' and mimeType='application/vnd.google-apps.folder' and trashed=false").execute()

        if len(folders.get("files")) == 1:
            return folders.get("files")[0].get("id")
        elif len(folders.get("files")) > 1:
            raise Exception(f"More than one folder with name {google_drive_folder} found!")
        else:
            print(folders)
            file_metadata = {
                "name": google_drive_folder,
                "mimeType": "application/vnd.google-apps.folder"
            }

            # pylint: disable=maybe-no-member
            folder = self.__client.files().create(body=file_metadata, fields='id').execute()

            return folder.get('id')

    def delete_all_videos_older_than(self, delete_before_date: datetime.datetime, google_drive_folder="recordings"):
        """
        Deletes all Google Drive files in
        :param google_drive_folder:
        :param delete_before_date:
        """
        folder_id = self.__get_folder_id(google_drive_folder)
        files_to_delete = self.__client.files().list(
            q=f"parents in '{folder_id}' and trashed=false and mimeType contains 'video/'").execute()
        for file in files_to_delete.get("files"):
            creation_date = datetime.datetime.fromisoformat(file.get("name")[0:-5])
            file_id = file.get("id")
            if creation_date <= delete_before_date:
                self.__client.files().delete(fileId=file_id).execute()
                print(f"Deleted file {file.get('name')} from Google Drive")

    def upload_video(self, file_path, file_name, google_drive_folder="recordings", mime_type="video/H264"):
        """
        Uploads a video to Google Drive.
        :param file_path: file path
        :param file_name: name of the file with extension
        :param google_drive_folder: name of the Google Drive folder
        :param mime_type: mime type of the file
        """
        try:
            folder_id = self.__get_or_create_folder(google_drive_folder=google_drive_folder)

            file_metadata = {"name": file_name, "parents": [folder_id]}
            media = MediaFileUpload(file_path,
                                    mimetype=mime_type)
            file = self.__client.files().create(body=file_metadata, media_body=media,
                                                fields="id").execute()
            print(f"Uploaded video with file ID: {file.get('id')}")

        except HttpError as error:
            print(f"An error occurred: {error}")
            file = None

        return file.get("id")
