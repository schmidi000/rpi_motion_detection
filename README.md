# Motion Detection with Raspberry Pi Camera Module v2

Supports upload of videos to Google Drive v3.

Based on [Picamera2 beta](https://github.com/raspberrypi/picamera2]).

Works with the camera module V2 and Debian "bullseye".

Check out how to configure the camera before
continuing: [how to configure the camera modules]( https://www.raspberrypi.com/documentation/accessories/camera.html#if-you-do-need-to-alter-the-configuration)

## How to run?

#### 1) Install Picamera2 package for Python

~~~
sudo apt-get install -y python3-picamera2
~~~

### 2) Run application

~~~
python3 main.py
~~~

## Start on boot

To start the motion detector on boot you have to follow those steps:

#### 1) ```mkdir ~/.config/autostart```

#### 2) ```nano ~/.config/autostart/MotionDetector.desktop```

#### 3) add the following content to the ```.desktop``` file:

~~~
[Desktop Entry]
Name=Motion Detector
Type=Application
Comment=RPI motion detection
Exec=/usr/bin/python3 /path/to/motion_detector.py arguments...
~~~

#### 4) make file executable: ```chmod +x ~/.config/autostart/MotionDetector.desktop```

## Command line arguments

#### Enable preview

Shows a preview window of what the camera sees.

~~~
python3 main.py --preview
~~~

#### Zoom camera (software-based)

Example of a x2 zoom:

~~~
python3 main.py --zoom 0.5
~~~

#### Motion detection sensitivity

If you want the motion detection to be more or less sensitive, you can do this as follows:

The lower, the more sensitive.

~~~
python3 main.py --min-pixel-diff 5.2
~~~

#### Google Drive upload

Uploads videos to Google Drive.

~~~
python3 main.py --drive-upload
~~~

#### Delete videos after upload

Deletes the local video after uploading it to Google Drive.

~~~
python3 main.py --drive-upload --delete-local-recordings-after-upload
~~~

#### Delete Google files older than

Automatically deletes videos stored on Google Drive that are older than 7 days:

~~~
python3 main.py --drive-upload --delete-recordings-after-seconds 604800
~~~

## Google Drive upload

For a detailed instruction, follow the
official [Google documentation](https://developers.google.com/drive/api/quickstart/python)

#### 1) Install Google Drive client for Python

~~~
  pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
~~~

#### 2) Enable Google Drive API on GCP

Sign in to [Google Cloud Platform](https://console.cloud.google.com/), search for "Google Drive API" and click "Enable".

#### 3) Create OAuth2 client for Drive API

After enabling the Google Drive API you have to generate an OAuth2 client.
Navigate to "Google Drive API" on Google Cloud Platform and click "Manage" -> "Credentials" -> "+ CREATE CREDENTIALS"
-> "OAuth client ID" -> select Application type "Desktop app".

Now that you have created an OAuth client you have to download the credentials. Click on the previously created client
-> "DOWNLOAD JSON".

The .json file has to be located in the same directory with the main.py.

To enable Google Drive upload start the application with the --drive-upload option.

~~~
python3 main.py --drive-upload
~~~

If this is your first time running the Google Drive sign in, you have to follow the instructions on the command line.

## Limit bandwidth
If you run your Raspberry in your home network, you probably want to limit the bandwidth. If you don't have a router with QoS, you can use tools like WonderShaper.

Follow those steps to enable traffic shaping on boot:
1) install WonderShaper
~~~
sudo apt-get install wondershaper
~~~

2) create file
~~~
sudo nano /etc/systemd/system/wondershaper.service
~~~

3) add the content
Here is an example systemd unit file that limits the upload and download speed of the "wlan0" interface to 2048 Kbps:
~~~
[Unit]
Description=Limit UL and DL to 2048kbps

[Service]
Type=simple
ExecStart=wondershaper wlan0 2048 2048

[Install]
WantedBy=multi-user.target
~~~

4) start service
~~~
sudo systemctl enable --now wondershaper.service
~~~