<!-- markdownlint-disable -->
<p align="center">
<img src="readme_medias\0_title.jpg" alt="0_title" width="100%">
</p>

<summary style="font-size:1.5em;font-weight:bold;"> 📑 Table of contents</summary>

- [🌏 Overview](#overview)
- [🏃‍♀️‍➡️ Getting Started](#getting-started)
  - [💻 Using the Packaged Application ](#using-the-packaged-application)
  - [🧑‍💻 Using the Source Code ](#using-the-source-code)
- [📄 Program Usage Guide](#program-usage-guide)
  - [😎 Key Features](#key-features)
  - [📣 Basic Operation Flow](#basic-operation-flow)
  - [🕵️ Common usage scenarios](#common_usage_scenarios)
- [📖 Dataset used for training the model](#dataset-used-for-training-the-model)
- [🧩 Software Architecture](#technical-architecture)
    - [🗃️ Code file structure](#code-file-structure)
- [📜 License](#license)
- [🤝 Contact Us](#contact-us)
---
<a id="overview"></a>
<summary style="font-size:1.5em;font-weight:bold;"> 🌏 Overview </summary>

- **StomataQuant is a graphical user interface (GUI) software specifically developed for processing and analyzing plant epidermal stomatal images.**
- **It integrates deep learning and computer vision techniques to automatically detect, segment, and quantify stomata, pores, and pavement cells on plant epidermis, and provides detailed measurement data.**
- **More importantly, StomataQuant also offers comprehensive and intuitive manual correction features, allowing users to directly adjust and edit the AI-generated results to ensure the accuracy and reliability of the analysis.**

<p align="center">
<img src="readme_medias\1_overview_demo_stomatadetect.gif" alt="1_overview_demo_stomatadetect" width="32%">
<img src="readme_medias\1_overview_demo_stoma_pore.gif" alt="1_overview_demo_stoma_pore" width="32%">
<img src="readme_medias\1_overview_demo_stoma_pvc.gif" alt="1_overview_demo_stoma_pvc" width="32%">
</p>

---

<a id="getting-started"></a>
<summary style="font-size:1.5em;font-weight:bold;">🏃‍♀️‍➡️ Getting Started</summary>

- **This program can be downloaded in two ways:**
   1. Download the [packaged application](#using-the-packaged-application) (**recommended for users without programming experience**); 
   2. Or download the [source code](#using-the-source-code) from GitHub.

<a id="using-the-packaged-application"></a>
<details>
<summary style="padding-left: 1em;"><strong>💻 Using the Packaged Application</strong></summary>

1. **Application Download**
    - **Windows**
        + CPU only Application (**Recommended, Most Stable**) | [Download](https://disk.pku.edu.cn/link/AA76003FFFD0504A64AA7AD59352886DE4)| Extract Code: `WoRM`
        + GPU Application (CUDA Version > 12.4) | [Download](https://disk.pku.edu.cn/link/AAD31BEA8CE1EE4C13991BE5F1C20C38F2) | Extract Code: `36Q2`
    - **macOS**
        + CPU only Application | [Download](https://disk.pku.edu.cn/link/AA02FD45ED0CEB4845986A61DEE9D7592C) | Extract Code: `Axi5`

2. **Model Weights Download**
    + You can choose different types of models according to your task, and select different-sized models based on the performance of your computer, from **n**(nano), **s**(small), m(medium), **l**(large), **xl**(extra large).
    - We recommend using the **xl**-sized model to achieve better inference results. However, the drawback is that without GPU acceleration, the inference time will be longer.
    + **All Models** | [Download](https://disk.pku.edu.cn/link/AA67C4E18F5DCC4D47ACECB4638BECD038) 
        + **Stomata Detection** | [Download](https://disk.pku.edu.cn/link/AABDB2D8A64C1047BC97E823E3551DCF8E) 
        + **Stoma and Pore Segmentation** | [Download](https://disk.pku.edu.cn/link/AA420808C46B864347AD09C42E1133AA0F) 
        + **Stoma and Pavement Cell Segmentation** | [Download](https://disk.pku.edu.cn/link/AADF39B88851B54E06AD9653CDC3028A6D) 

3. **Before Running the Packaged Application (Preliminary Steps)**


<details>
<summary style="padding-left: 3em;"><strong>&nbsp;&nbsp;&nbsp;&nbsp; Windows:</strong></summary>

- After downloading, extract the files to a folder. 
    - Using the default decompression tool provided by the Windows 11 system might be rather slow. It is recommended to use a dedicated decompression tool instead. **Important:** Ensure that the file path contains **no special characters or Chinese characters.**
    - The app folder contains the executable, source code (in the `src` subfolder), and a specific Python interpreter (in the `Python` subfolder). **Do not rename or modify these folders unless you intend to change the application's functionality.**
    - To run the application without making any modifications, simply execute either `StomataQuant_c.exe` or `StomataQuant_GPU_c.exe`.
    - Upon running the program, a **terminal** window will open to display program-related information. You can **minimize this window but do not close it**.

<p align="center">
<img src="readme_medias\2_windows_startup.gif" alt="2_windows_startup" width="70%">
</p>

</details>


<details>
<summary style="padding-left: 3em;"><strong> &nbsp;&nbsp;&nbsp;&nbsp; macOS:</strong></summary>


- **After downloading, you need to make the application executable**
1. Open the terminal. Navigate to the directory where you downloaded the file. Run the following command to make SQ_Mac executable:
```bash
chmod +x SQ_Mac
```
- This command grants **execute permissions** to the SQ_Mac file.

2. Run the program. You might need to allow the program to run in your system's  Security & Privacy settings if it was downloaded from an external source. This is a standard macOS security measure.

<p align="center">
<img src="readme_medias\2_macos_download_chmod+x.gif" alt="2_macos_download_chmod+x" width="50%">
<img src="readme_medias\2_mac_os_privacy.png" alt="2_mac_os_privacy" width="32%">
</p>


3. Upon running the program, a **terminal** window will open to display program-related information. You can **minimize this window but do not close it**. Wait for the program to launch. Note that startup on macOS might take longer due to system checks and package loading."


<p align="center">
<img src="readme_medias\2_mac_os_cml_open.png" alt="2_mac_os_cml_open" width="40%">
<img src="readme_medias\2_macos_startup.gif" alt="2_macos_startup" width="48%">
</p>
</details>

</details>


<a id="using-the-source-code"></a>
<details>
<summary style="padding-left: 1em;"><strong>🧑‍💻 Using the Source Code </strong></summary>

1. **Clone the repository**
    ```
    git clone https://github.com/Milo-L/StomataQuant.git
    ```
2. **Install dependencies**
    ```
    pip install -r SQ_gpu_requirements.txt
    ```
    or
    ```
    pip install -r SQ_cpu_requirements.txt
    ```
3. **Run the application using your Python interpreter, and don't forget to download the necessary [model files](#using-the-packaged-application)**
    ```
    python Load_StomataQuant_GUI.py
    ```
</details>

---
<a id="program-usage-guide"></a>
<summary style="font-size:1.5em;font-weight:bold;">📄 Program Usage Guide</summary>
<a id="key-features"></a>
<details>
<summary style="padding-left: 1em;"><strong>😎 Key Features</strong></summary>

1. **AI-driven Detection and Segmentation:** 
    - Integrates YOLO object detection and segmentation models for automated stomata detection and stoma, pore, and pavement cell segmentation.
2. **Result Editing Capability:** 
    - Allows for manual verification and editing of AI inference outcomes.
3. **Measurement and Analysis:**
    - Extraction of shape features such as count, area, perimeter, etc., with the available features varying depending on the shape type.
4. **Comprehensive Annotation Tools and Management:**
    - Offers a variety of manual annotation tools, including polygons, rectangles, rotated rectangles, lines, and points, with integrated support for importing and exporting these annotation types.
5. **Batch Processing Capability:** 
    - Allows for automated execution of model inference and analysis tasks on multiple loaded images.
6. **Heatmap Generation:** 
    - Generates feature distribution heatmaps for intuitive visualization of analysis results (as depicted in following figure ).

<p align="center">
<img src="readme_medias\3_heatmap_generated_by_StomataQuant.jpg" alt="3_heatmap_generated_by_StomataQuant" width="70%">
</p>
</details>

<a id="basic-operation-flow"></a>
<summary style="padding-left: 1em;"><strong>📣 Basic Operation Flow</strong></summary>
<details>
<summary style="padding-left: 1.5em;"><strong>01. Load Images</strong></summary>

+ Click ``File`` → ```Open images```
+ Select the images to be analyzed
+ The images will be displayed in the main window and can be managed through tabs
<p align="center">
<img src="readme_medias\3_openfile.gif" alt="3_openfile" width="70%">
</p>
</details>

<details>
<summary style="padding-left: 1.5em;"><strong>02. Select Model Based on Purpose</strong></summary>

- Click `Setting`→`Model Setting`
    - If you are focusing on the number or distribution of stomata, or measuring stomatal density:
        - → Select `stomata detection model`
        - The inference result will be **rectangle** bounding boxes around potential stomatal complexes.
    - If you are focusing on stomatal or pore size, or measuring stomatal aperture or size:
        - → Select `stoma and pore segmentation model`
        - The inference result will be **polygon** shapes outlining potential stomata and their pores.
    - If you are focusing on pavement cells, or measuring stomatal index and pavement cell shape descriptors:
        - → Select `stoma and pavement cell segmentation model`
        - The inference result will be **polygon** shapes outlining potential stomatal complexes and pavement cells.
</details>

<details>
<summary style="padding-left: 1.5em;"><strong>03. AI Inference</strong></summary>

- Click `AI😎` button → Run inference to execute automatic detection or segmentation
- Inference results will be directly displayed on the image as shown in the following figures

<p align="center">
<img src="readme_medias\3_detect_model.gif" alt="3_detect_model" width="32%">
<img src="readme_medias\3_stoma_pore_model.gif" alt="3_stoma_pore_model" width="32%">
<img src="readme_medias\3_stoma_pvc_model.gif" alt="3_stoma_pvc_model" width="32%">
</p>
</details>

<details>
<summary style="padding-left: 1.5em;"><strong>04. Confirm Inference Results (Optional)</strong></summary>

- Confirm whether the inference results are correct
- If errors occur, the corresponding shapes can be [edited](#shape-editing) manually
</details>

<details>
<summary style="padding-left: 1.5em;"><strong>05. Feature Extraction</strong></summary>

1. Set the scale: `Analyze` → `Set Measuring Scale`
2. Click `Feature Extraction` button
3. The results will be displayed on the right-side `ResultsSummary` and `MeasuredResults` sub-windows
4. You can choose to copy or export the results to a CSV file

<p align="center">
<img src="readme_medias\3_getfeature1.jpg" alt="3_getfeature1" width="32%">
<img src="readme_medias\3_getfeature2.jpg" alt="3_getfeature2" width="32%">
<img src="readme_medias\3_getfeature3.jpg" alt="3_getfeature3" width="32%">
</p>
</details>

<details>
<summary style="padding-left: 1.5em;"><strong>Workflow Summary</strong></summary>
<p align="center">
<img src="readme_medias\3_workflow.jpg" alt="3_workflow" width="70%">
</p>
</details>




<a id="common_usage_scenarios"></a>

<summary style="padding-left: 1em;"><strong>🕵️ Common usage scenarios</strong></summary>

<details>
<summary style="padding-left: 1.5em;"><strong>Rapid measurement of stomatal aperture or size</strong></summary>

- If you want to **measure stomatal aperture or size** and quickly edit inference results:
    1. You can use the `GetMER` button after model inference to obtain the minimum bounding rotated rectangle of the polygons;
    2. You can set the polygons to be invisible and only display the rotated rectangles for quick editing;
    3. After editing, click `Feature Extraction` to quickly obtain stomatal aperture and size data.

<p align="center">
<img src="readme_medias\3_rapid_stomatal_apeature.gif" alt="3_rapid_stomatal_apeature" width="70%">
</p>
</details>

<details>
<summary style="padding-left: 1.5em;"><strong>Rapid measurement of stomatal index</strong></summary>

- If you want to quickly **measure the stomatal index** and edit the inference results, you can use `Analyze`→ `Shape Filter` to select the shapes you want to filter out that are located on certain edges after model inference;
- Then you can use `View`→`All shapes are displayed as points` to replace each shape (each represents a cell) with a point;
- Next, confirm and count the cells by adding or deleting points;
- Finally, calculate the stomatal index based on the number of stomata and pavement cells.
<p align="center">
<img src="readme_medias\3_rapid_stomatal_index.gif" alt="3_rapid_stomatal_index" width="70%">
</p>
</details>

<details>
<summary style="padding-left: 1.5em;"><strong>Heatmap generation</strong></summary>

- After completing polygon feature extraction;
- Click `View` → `Heatmap of polygon features`;
- Select the **feature type** and **color scheme** for the heatmap, as well as the **output location**;
- Then, wait for the generation of the heatmap.
<p align="center">
<img src="readme_medias\3_heatmap_generated.gif" alt="3_heatmap_generated" width="70%">
</p>
</details>

<details>
<summary style="padding-left: 1.5em;"><strong>Batch processing</strong></summary>

- Open multiple image tabs;
- Click `More` → `Batch Processing`;
- Select the operation you want to be performed (**AI inference, feature extraction, etc.**), as illustrated on the left;
- And initiate batch processing. The example on the right showcases the rapid determination of stomatal aperture **in batches**.
<p align="center">
<img src="readme_medias\3_BatchProcess.jpg" alt="3_BatchProcess" width="49%">
<img src="readme_medias\3_batch_example.gif" alt="3_batch_example" width="49%">
</p>
</details>

<details>
<summary style="padding-left: 1.5em;"><strong>Shape Creation</strong></summary>

- Supports creating **polygons, rotated rectangles, rectangles, lines, and points**.
    - **Create Polygon:**
        1. Click `Create`→`Create Polygon`;
        2. `Left-click` on the image to start drawing, and each `left-click` creates a vertex of the polygon;
        3. After creating the polygon, you can quickly finish drawing by **double-clicking** or by `clicking the first point` to finish the shape.
    - **Create RotatedRectangle:**
        1. Click `Create`→`Create RotatedRectangle`;
        2. `Left-click` to set the first point of the rotated rectangle, `release` the left mouse button to record the second point, which defines one side of the rotated rectangle;
        3. Click again to define the entire rotated rectangle.
    <p align="center">
    <img src="readme_medias\3c_create_polygon.gif" alt="3c_create_polygon" width="49%">
    <img src="readme_medias\3c_create_rotatedrectangle.gif" alt="3c_create_rotatedrectangle" width="49%">
    </p>       

    - **Create Rectangle:**
        1. Click `Create`→`Create Rectangle`;
        2. `Left-click` to set the top-left corner of the rectangle;
        3. `Release` the left mouse button to set the bottom-right corner of the rectangle, completing the creation.
    - **Create Line:**
        1. Click `Create`→`Create Line`;
        2. `Left-click` to confirm one point of the line;
        3. `Release` the left mouse button to confirm the other point of the line, completing the creation.
    - **Create Point:**
        1. Click `Create`→`Create Point`;
        2. `Left-click` to create a point.
    <p align="center">
    <img src="readme_medias\3c_create_rectangle.gif" alt="3c_create_rectangle" width="32%">
    <img src="readme_medias\3c_create_line.gif" alt="3c_create_line" width="32%">
    <img src="readme_medias\3c_create_point.gif" alt="3c_create_point" width="32%">
    </p>
</details>
<a id="shape-editing"></a>
<details>
<summary style="padding-left: 1.5em;"><strong>Shape Editing</strong></summary>

- Supports editing **polygons, rotated rectangles, rectangles, lines, and points.**
    - After selecting a shape, click the `Delete` button or press the `Delete` or `Backspace` key on the keyboard to delete it;
    - Press `Ctrl + C` or the `Duplicate` button to copy the shape;
    - `Left-click` and drag the inside of a shape to move it.

- **Edit Polygon:**
    - `Left-click` and drag an endpoint to move it;
    - Right-click on an endpoint to delete the vertex;
    - `Ctrl + Right-click` on an endpoint to delete multiple vertices in batch;
    - `Left-click` on the line segment between two endpoints to add a new endpoint.

- **Edit RotatedRectangle:**
    - `Left-click` and drag an endpoint to scale the rotated rectangle;
    - `Left-click` and drag the rotation control point to rotate the rotated rectangle.

<p align="center">
<img src="readme_medias\3e_edit_polygon.gif" alt="3e_edit_polygon" width="49%">
<img src="readme_medias\3e_edit_rotatedrectangle.gif" alt="3e_edit_rotatedrectangle" width="49%">
</p>     

- **Edit Rectangle:**
    - `Left-click` and drag an endpoint to scale the rectangle;

- **Edit Line:**
    - `Left-click` and drag its endpoint to move the endpoint;
    - Click on the midpoint of the line to move the line segment.
- **Edit Point:**
    - `Left-click` and drag to move the point.

<p align="center">
<img src="readme_medias\3e_edit_rectangle.gif" alt="3e_edit_rectangle" width="32%">
<img src="readme_medias\3e_edit_line.gif" alt="3e_edit_line" width="32%">
<img src="readme_medias\3e_edit_point.gif" alt="3e_edit_point" width="32%">
</p>
</details>

<details>
<summary style="padding-left: 1.5em;"><strong>Shape Annotation Import and Export</strong></summary>

- The ability to import or save annotations from external sources is crucial, whether for archiving measurement results or for accumulating data to [train and fine-tune future models](#train-a-new-model).
    - Supports importing and exporting annotations for a **single image**;
    - Also supports **exporting shape annotations** for all images currently open in tabs;
    - Also supports **batch importing annotations** and opening images.
    - Currently, annotation import and export only supports **YOLO format** for **Rectangle, RotatedRectangle (OBB), and Polygon**.
</details>
<a id="train-a-new-model"></a>
<details>
<summary style="padding-left: 1.5em;"><strong>Training New Models and Contributing</strong></summary>

- To train a new model or fine-tune an existing one, please refer to the official [Ultralytics training documentation](https://docs.ultralytics.com/modes/train/), which offers comprehensive guidance on dataset preparation, training parameter configuration, and the training process itself.

- **If you're interested in contributing to StomataQuant, you can prepare annotated datasets and [contact us](#contact-us). We plan to release next-generation models for community use in the future.**
</details>

---
<a id="dataset-used-for-training-the-model"></a>
<summary style="font-size:1.5em;font-weight:bold;">📖 Dataset used for training the model</summary>

- Dataset for the stomata detection model | [Download]()
- Dataset for the stoma and pore segmentation model | [Download]()
- Dataset for the stoma and pavement cell segmentation model | [Download]()
<p align="center">
<img src="readme_medias\4_dataset.jpg" alt="4_dataset" width="70%">
</p>

<a id="technical-architecture"></a>
<summary style="font-size:1.5em;font-weight:bold;">🧩 Software Architecture</summary>

- **UI framework**: [PyQt5](https://www.riverbankcomputing.com/static/Docs/PyQt5/)
- **Deep Learning Model Training and  Inference**: [YOLOv11 (Ultralytics)](https://github.com/ultralytics/ultralytics)
- **Shape and Data Analysis**:
    - [OpenCV](https://github.com/opencv/opencv)
    - [PIL (Pillow)](https://github.com/python-pillow/Pillow)
    - [NumPy](https://github.com/numpy/numpy)
    - [shapely](https://github.com/shapely/shapely)
- **Program Acceleration**: [numba](https://github.com/numba/numba)
- **Heatmap Visualization**: [Matplotlib](https://github.com/matplotlib/matplotlib)
<a id="code-file-structure"></a>
<details>
<summary style="padding-left: 1em;"><strong>🗃️ Code file structure</strong></summary>

- StomataQuant-GUI is designed with a **modular architecture**, consisting of the following key components:
1. **Main Application Files**
    - **`Load_StomataQuant_GUI.py`**: Entry point of the application, responsible for loading and initializing the main application window. Contains the `UIMainWindow` class that implements most core functionalities and event handling.
    - **`StomataQuant_GUI.py`**: Contains the `MainWindow` class which sets up basic UI elements including menu bars, toolbars, status bars, and initial layouts.

2. **Graphics and Drawing Components**
    - **`shape.py`**: Defines the `Shape` class representing various graphical objects (polygons, rectangles, rotated rectangles, lines, points, etc.). Implements drawing, feature extraction, and geometric operation methods.
    - **`canvas.py`**: Implements the `Canvas` class serving as the main drawing area. Handles mouse events, shape creation, editing, and user interactions.
    - **`ImageGraphicsView.py`**: Provides the `ImageGraphicsView` class that manages image display, zooming, and image-related interaction functionalities.

3. **Inference and Processing Components**
    - **`InferenceThread.py`**: Contains thread implementations for AI and image processing:
        - `YOLOSegInferenceThread`: Performs YOLO segmentation inference
        - `PolygonProcessThread`: Processes polygon data
        - `ABorADInferenceThread`: Performs AD and AB classification
        - `HeatMapGenerationThread`: Generates heat maps

4. **Interface Components**
    - **`dock_widgets.py`**: Implements multiple dock windows:
        - `ShapeListDock`: Displays current shape list
        - `LabelListDock`: Manages labels
        - `MeasuredResultsDock`: Shows measurement results of shapes
        - `ImageResultsSummaryDock`: Displays image analysis summary

5. **Batch Processing Functionality**
    - **`BatchProcessor.py`**: Implements batch processing features:
        - `BatchProcessor`: Performs operations on multiple tabs
        - `BatchExporter`: Exports annotations in bulk
        - `BatchImporter`: Imports annotations and images in bulk

6. **Dialog Components**
    - **`AllDialogs.py`**: Contains various dialogs:
        - `BatchProcessingDialog`: Batch processing settings
        - `BatchProgressDialog`: Batch processing progress display
        - `InferenceSettingsDialog`: Inference settings
        - `SetMeasuringScaleDialog`: Measurement scale settings
        - `LabelInputDialog`: Label input
        - `ColorSettingsDialog`: Color settings
        - `HeatMapDialog`: Heat map generation settings

7. **Resources**
    - **`resources_rc.py`**: Contains compiled resources for the application (icons, images, etc.), generated from Qt Resource Collection (.qrc) files. Used to embed binary resources that can be accessed with the ":/resource_path" notation throughout the application.
</details>


<a id="license"></a>
<summary style="font-size:1.5em;font-weight:bold;">📜 License</summary>

- This project uses the **AGPL-3.0 license**. Any derivative works based on this project must:
  - Disclose the complete source code;
  - Include the original copyright notice;
  - Commercial use requires contacting the author for special authorization.


<a id="contact-us"></a>
<summary style="font-size:1.5em;font-weight:bold;">🤝 Contact Us</summary>

- For any questions or suggestions, please submit an [issue](https://github.com/Milo-L/StomataQuant/issues) or contact [Menglong Liu](https://github.com/Milo-L/) ([milo.liu@stu.pku.edu.cn](mailto:milo.liu@stu.pku.edu.cn))  or [Dr. Yin Wang](https://www.researchgate.net/profile/Yin-Wang-78) ([wangyinpku@pku.edu.cn](mailto:wangyinpku@pku.edu.cn)).

---
<p align="center">
<img src="readme_medias\8_bottom.jpg" alt="8_bottom" width="100%">
</p>
