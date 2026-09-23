[Español](../README.md) | **English**

# AGU printer film scanner
Digitizing photochemical film is a need shared by all archives and collections.
Although the cost of the necessary equipment has dropped considerably in recent years, it remains inaccessible for small archives and collections.
With this in mind, at the University Document Digitization Space of the General Archive of UDELAR we set out to develop a low-cost scanning system that other institutions and individuals can replicate, while meeting certain quality and sustainability criteria.

<img width="400" height="200" alt="image2" src="https://github.com/user-attachments/assets/bc887b72-1014-4087-983f-aca6ca5a7e00" />


## Components

<img width="400" height="400" alt="image6" src="https://github.com/user-attachments/assets/871c9989-c511-47bc-9ca4-4892228428dd" />

1. A receipt/ticket printer of the kind used at point-of-sale terminals.

<img width="400" height="400" alt="image12" src="https://github.com/user-attachments/assets/7a4aabcb-5ffc-4c54-8df3-e3bd50ba3120" />

2. A digital camera compatible with [gphoto2](http://www.gphoto.org/proj/libgphoto2/support.php).

3. A macro lens or extension tubes.

4. A mid-range computer running Ubuntu.

<img width="400" height="400" alt="image4" src="https://github.com/user-attachments/assets/d74d393f-e265-4def-9b87-aed1b4be190d" />

5. A square LED panel light approximately 11 cm on each side.

<img width="400" height="400" alt="image5" src="https://github.com/user-attachments/assets/ffe8d74a-c20d-4cf4-a881-b4dbdbc86906" />


6. Parts that were 3D-printed:
Support and handles for the LED panel.

Base, lid, and locks for 16mm and 35mm film.

7. A wooden board as a base for all the components.

8. An enlarger stand as a camera support.

9. Two old film rewinders.

## Operating principle

<img width="400" height="250" alt="image11" src="https://github.com/user-attachments/assets/dec98bf0-89c8-4cfe-98f9-80574b886b9a" />

The printer’s paper-feed mechanism is used to advance the film. This requires a few minor modifications:

1. Cover the paper-out sensor with adhesive tape.

<img width="400" height="266" alt="image3" src="https://github.com/user-attachments/assets/645053f8-d7e1-42b8-ade5-4661f911b810" />


2. Make a small cut in the plastic cover where the film will enter.

<img width="400" height="250" alt="image1" src="https://github.com/user-attachments/assets/374d10af-6c2e-4d45-8560-35b4e514d069" />

3. Remove the lid hinge pin so the lid can be taken off when threading the film.

<img width="400" height="250" alt="image10" src="https://github.com/user-attachments/assets/e3858138-cb60-41f1-a4c9-4b02f391b6bd" />

This process does not require a ticket printer specifically; any generic thermal printer can be used. However, the modifications may need to be adapted to the printer’s shape.

4. A generic LED panel is used as the light source.

5. 3D-printed parts are made to place the light source at the same height as the film entry into the printer, plus guides to carry the film over the window cut into the support.

<em>The .stl files are in the repository’s <a href="./">docs</a> folder</em>

6. The camera with a macro lens is placed on the stand at a suitable height to frame the frame. In our case we used the stand from an old photographic enlarger to hold the camera.

<img width="400" height="605" alt="image7" src="https://github.com/user-attachments/assets/94201f88-8134-4422-a704-b85cb33fea67" />


7. Both the camera and the printer connect to the computer via USB cables, so no extra wiring or soldering is required.

## Software

<img width="400" height="250" alt="Print-Scanner_en" src="https://github.com/user-attachments/assets/5ecd8ca8-35b2-4c0c-b19b-44f6ae68849c" />


The entire system is controlled by an app that drives the camera through the gphoto2 library and processes images with OpenCV. For now, this app only runs on Linux, but it can be ported to macOS.

When you use the software for the first time, you need to enter:

1. The camera serial number
2. The reference-code prefix (e.g. UY-UDELAR-AGU-AIH). Our entire holdings fall under this code, so we use it as the prefix for all digitizations.
3. Select the directory where images will be saved.
4. Enter the reference code to scan (what follows the prefix — e.g. I-AGU-02-01)
5. Then select the film format. For now, the system works with 16 mm film (work is underway to include 35 mm as well, although it has not yet been tested with the archive’s holdings). In the future it will also support 8 mm and Super 8 film.
 
Once the format is selected, the program interface shows the live view from the camera with three blue lines overlaid on the live view, used to align the camera with the film, the red area where the system looks for the perforation, plus some configuration and playback buttons in the lower-right of the screen and, along the bottom, four buttons (Digitize, Pause, Move 1px, and Frame x Frame).

Before starting, you need to adjust focus and other camera settings.
This is done through Entangle, which you can open with the “Settings” button (E key). After making the adjustments, return to the live view and set the threshold level (Y key) so perforations can be detected. Once the threshold level is set, you must configure the minimum number of white pixels. To do this, enable “Enable Debug” (or the G key); the screen will turn red, and start digitization (Z key).
Two windows then open: one with the analyzed data, and another showing what is being detected in the perforation search area.
At that point you can take three actions:
1. Close the windows with the Q key.
2. Advance the film by one pixel so it re-analyzes the new position with the E key _(Only works in debug mode)_.
3. Turn off Debug mode and resume normal digitization with the R key.

What matters at this stage is advancing one pixel until the perforation is fully visible in the search window, so you can see the white-pixel count and enter that value, or a few pixels fewer, in the “White Px Threshold” option (U key). Then, if everything looks correct, you can start scanning.

The “Move 1px” button (C key) advances one pixel at a time until the point where you want digitization to begin.
The “Pause” button (P key) pauses digitization at any time.
To start scanning, click the “Digitize” button (Z key).
 
## Scanning

Scanning starts by identifying the perforation by counting white pixels in the area marked with the red box. If the perforation is not identified, the printer advances the film one pixel at a time until it finds the perforation.

For cases with more than one perforation per frame, such as 35 mm film, the system counts perforations until it identifies a frame change. After that, the digitization process is the same.

For now, the reels have no motors, so a person must feed and take up the film manually. To speed up scanning, the system does not save images to the destination folder; instead, the raw files (tif, cr3, or others depending on the camera) are stored on the camera’s memory card, and a mapping is kept between the camera’s image name and the name it should have. When there is a raw file on the camera, the “Download RAWs” button turns red, indicating pending downloads.

During scanning you need to clean the whole system every so many photos, so we configured it to stop every 500 frames. Using air (a rubber blower or compressed air), clean the capture area, removing any debris that may have come off the film. We also use that pause to download the raw images; the system downloads them and renames them with the name and number that were configured.
 
## Post-production

Once film scanning is finished, you get a sequence of digital photos numbered to match the photochemical frames of the original film. After that, a digital stabilization process is needed to correct the small misalignments in the digital captures. One option is DaVinci Resolve, which has a free version.
 
## Advantages and disadvantages

The main advantage of this system is its low cost. The most expensive component is the camera, although a simple camera that is gphoto2-compatible and has a macro lens can be used. Because the system is modular, it can be improved gradually if a larger budget becomes available. At AGU we used a discontinued mirrorless camera with 32 megapixels, enough for 4K resolution (approx. USD 700), a 50 mm lens (approx. USD 300), and extension tubes (approx. USD 100). The computer used is one already available in the archive, about four years old. The 3D-printed parts were made on a very basic machine that cost about USD 300, although they can also be produced through external printing services.

Another advantage is simplicity: advanced IT knowledge is not required to install and operate the system. The system is also versatile. Although the design was initially developed for digitizing 16 mm film—the bulk of AGU’s holdings—the guides and the app can be adapted for other formats.

A disadvantage is that, for now, the system can only be used on Ubuntu. Although it can be migrated to macOS with some modifications, it still cannot run on Windows, because the gphoto2 library is not compatible with that environment.
 
## Next steps

As mentioned earlier, this is a project under development. After testing it over the past months we identified some improvements to make:
- Motorize the film supply reels.
- Develop the adaptation for 35 mm and 8 mm film.
- Cosmetic improvements to the user interface.


## App installation, configuration, and run guide

This document provides the steps needed to prepare and run the app correctly.

## Step 1: Install Python 3

Make sure Python 3 is installed on your system. You can install it from apt using the terminal.

   ```bash
   sudo apt update
   sudo apt install python3 python3-pip
   ```

To verify that python3 was installed correctly, run the following command in the terminal:
   ```bash
   python3 --version
   ```

## Step 2: Install app dependencies

1. **Install system packages and desktop shortcut:**

   Open a terminal and, from the repository root, run the following command to install the app dependencies:

   ```bash
   python3 print_scanner_app/installer/install.py
   ```

2. **Verify the desktop shortcut:**

   You should now see the shortcut on your desktop. Double-click it to run the program.

## Step 3: Get the camera serial number using the terminal

1. **Connect the camera:**

   Make sure your camera is connected to your computer’s USB port.

2. **List connected devices:**

   Run the following command to list connected devices and verify that your camera is recognized:

   ```bash
   gphoto2 --auto-detect
   ```

   This should show a list of connected devices, including your camera.

3. **Get the serial number:**

   Once you have confirmed that the camera is connected and recognized, run the following command to get the serial number:

   ```bash
   gphoto2 --get-config serialnumber
   ```

   This command should return the camera’s serial number.

   When you start the program it will ask for the camera serial number if it is not set in the config.json file.

---

With these steps completed, you should be ready to run the app without issues.
If you run into problems, review each step to make sure everything is configured correctly.
