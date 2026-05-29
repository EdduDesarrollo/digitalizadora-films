# AGU printer film scanner
Digitizing photochemical film is essential for all archives and collections.

Although the cost of the necessary equipment has decreased considerably in recent years, it remains inaccessible to small archives and collections.
With this in mind, at the University Document Digitization Space of the General Archive of UDELAR, we have dedicated ourselves to developing a low-cost scanning system that can be replicated by other institutions and individuals while meeting certain quality and sustainability criteria.

<img width="400" height="200" alt="image2" src="https://github.com/user-attachments/assets/bc887b72-1014-4087-983f-aca6ca5a7e00" />


## Components

<img width="400" height="400" alt="image6" src="https://github.com/user-attachments/assets/871c9989-c511-47bc-9ca4-4892228428dd" />

1. A ticket printer of the kind used in sales stands.

<img width="400" height="400" alt="image12" src="https://github.com/user-attachments/assets/7a4aabcb-5ffc-4c54-8df3-e3bd50ba3120" />

2. A digital camera compatible with gphoto2 software. http://www.gphoto.org/proj/libgphoto2/support.php

3. A macro lens or extension tubes.

4. A mid-range computer with the Ubuntu operating system.

<img width="400" height="400" alt="image4" src="https://github.com/user-attachments/assets/d74d393f-e265-4def-9b87-aed1b4be190d" />

5. A square LED ceiling light approximately 11 cm on each side.

<img width="400" height="400" alt="image5" src="https://github.com/user-attachments/assets/ffe8d74a-c20d-4cf4-a881-b4dbdbc86906" />

6. 3D Printed Parts:
Support and handles for the ceiling light.

Base, lid, and clips for 16mm and 35mm film.

7. A wooden board as a base for all the elements.

8. An enlarger stand as a camera support.

9. Two old film rewinders.

## Operating Principle

<img width="400" height="250" alt="image11" src="https://github.com/user-attachments/assets/dec98bf0-89c8-4cfe-98f9-80574b886b9a" />

The printer's paper feed mechanism is used to pull the film. This requires a few minor modifications:

1. Cover the paper-out sensor with an adhesive.

<img width="400" height="266" alt="image3" src="https://github.com/user-attachments/assets/645053f8-d7e1-42b8-ade5-4661f911b810" />

2. Make a small cut in the plastic cover where the film will be inserted.


<img width="400" height="250" alt="image1" src="https://github.com/user-attachments/assets/374d10af-6c2e-4d45-8560-35b4e514d069" />

3. Remove the lid's pivot point so it can be removed when threading the film.

<img width="400" height="250" alt="image10" src="https://github.com/user-attachments/assets/e3858138-cb60-41f1-a4c9-4b02f391b6bd" />

This process doesn't require a ticket printer; any generic thermal printer can be used. However, modifications may need to be adapted to the printer's shape.


4. A generic LED ceiling light is used as the light source.

5. 3D printed parts are used to position the light source at the same height as the film feed point on the printer, along with guides to guide the film onto the window cut into the film holder.

3D model of the 16mm film guide

6. The camera with a macro lens is placed on the stand at a suitable height for framing the image. In our case, we used a stand from an old photographic enlarger to support the camera.

<img width="400" height="605" alt="image7" src="https://github.com/user-attachments/assets/94201f88-8134-4422-a704-b85cb33fea67" />

7. Both the camera and the printer connect to the computer via USB cables, so no additional connections or soldering are required.

## Software

<img width="400" height="250" alt="image8" src="https://github.com/user-attachments/assets/c68448fa-8f84-40d0-b1d9-6abe2b21a64f" />

The entire system is managed by a Python script that controls the camera using the gphoto2 library and manipulates the images using OpenCV. Currently, this script only works on Linux operating systems, but it is possible to port it to macOS.

When you start using the software, you need to enter the reference code to be scanned and specify the path where the frame images will be saved. Then, you must select the film format. Currently, the system works with 16mm film (work is underway to include 35mm film as well, although it has not yet been tested with the archive's collection). In the future, it will also be possible to work with 8mm and Super 8 film.

Once the format is selected, the program interface will display the live view captured by the camera with three red lines superimposed on it, which are used to align the camera with the subject.
