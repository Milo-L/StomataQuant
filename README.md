
<!-- markdownlint-disable -->
<p align="center">
<img src="readme_medias\0_title.jpg" alt="0_title" width="100%">
</p>


[![Paper](https://img.shields.io/badge/Method%20Paper-Journal%20of%20Plant%20Ecology-green)](#citation)

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
- [📑 Citation](#citation)
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

1. **This program can be downloaded in two ways:**  
    1. Download the [packaged application](#using-the-packaged-application) (**recommended for users without programming experience**);  
    2. Or download the [source code](#using-the-source-code) from GitHub (**recommended if you plan to use GPU acceleration**).

2. **Model Weights Download**
    > This tool is powered by a **YOLO-based model**. Therefore, in addition to the software itself, you also need to download the **corresponding model weights** for your specific task in order to run AI inference. The basic usage workflow can be found [here](#basic-operation-flow).
    > You can choose different types of models according to your task and select different model sizes based on the performance of your computer: **n** (nano), **s** (small), **m** (medium), **l** (large), and **xl** (extra large).

    - We recommend using the **xl** model to achieve better inference performance. However, when running on **CPU only**, larger models may result in longer inference times.

        + **All Models** | [Download](https://disk.pku.edu.cn/link/AAC44553ECE969443AA3FB5471613AE9EC) | Extract Code: `0Qr2`  

            + **Stomata Detection** | [Download]( https://disk.pku.edu.cn/link/AA2BA08969302A4DF18131895C5FDC2F3A) | Extract Code: `N2D2`  
            + **Stomata and Pores Segmentation** | [Download](https://disk.pku.edu.cn/link/AA7C4E6A7F2FD84189A80655F6E6D1F25D) | Extract Code: `J63U`  
            + **Stomata and Pavement Cells Segmentation** | [Download](https://disk.pku.edu.cn/link/AA4F0255457A324A50834D4024CB124688) | Extract Code: `3v3S`


<a id="using-the-packaged-application"></a>
<details>
<summary style="padding-left: 1em;"><strong>💻 Using the Packaged Application</strong></summary>

1. **Application Download**
   - **Windows**
     + Windows Installer (CPU Version) (**Recommended, Most Stable**) | [Download](https://disk.pku.edu.cn/link/AA58997F2ED5BC47FD84725FD99C340CDA) | Extract Code: `JgEB`

    - Note:
       > Currently, the packaged installer is only available for the CPU version. GPU acceleration depends on compatible **CUDA, PyTorch, and NVIDIA driver versions**, which can vary across different Windows systems. If you would like to use GPU acceleration for faster inference, we recommend downloading the **[source code](#using-the-source-code)** and configuring the environment according to your local CUDA setup.

   - **macOS: CPU-only Version**
        + CPU-only Application  | [Download](https://disk.pku.edu.cn/link/AA9585CFC7A02B4A3EA0AC6D458530D7C1) | Extract Code: `UXqY`
        
        > Note: The macOS version is provided as a standalone Unix executable. Because it is not from the App Store, macOS will require manual permission to run.


2. **Before Running the Packaged Application (Preliminary Steps)**
<details>
<summary style="padding-left: 3em;"><strong>&nbsp;&nbsp;&nbsp;&nbsp; Windows:</strong></summary>

- **Step 1: Run the Installer & Choose Path**
  - Double-click the downloaded `StomataQuant-1.0-Windows-CPU-Setup.exe` installer. You can choose your preferred installation path. 
  - Click "Next"...... "Next" and then "Install".

<p align="center">
<img src="readme_medias\choose_your_work_path.png" alt="choose_your_work_path" width="48%">

<img src="readme_medias\next_and_next..._and_click install.png" alt="click_install" width="48%">
</p>


- **Step 2: Wait for Installation to Complete**
  - Please be patient while the installer extracts the deep learning environment and core files. Once the progress bar is full, the installation is successful.

<p align="center">
<img src="readme_medias\and waiting for_its ok.png" alt="waiting_for_install" width="48%">
<img src="readme_medias\when_its_ok.png" alt="install_success" width="48%">
</p>

- **Step 3: Launch and Use**
  - Launch **StomataQuant** directly by double-clicking the shortcut generated on your Desktop.
  - ⚠️ **Important:** A black command-line (terminal) window will pop up. **Please DO NOT close it!** This is a normal background process used for outputting debugging logs. You can simply minimize it.
  - The initial startup might take a few moments as it initializes the environment. Please be patient. Once the GUI appears, you are ready to go!

<p align="center">
<img src="readme_medias\dontworry_youll_find_blackcommandline_isfordebug_and_dontclose.png" alt="black_commandline" width="48%">
<img src="readme_medias\the_first_open_is_slow_but_be_paint_and_youcanuse_it.png" alt="first_open_gui" width="48%">
</p>

</details>


<details>
<summary style="padding-left: 3em;"><strong> &nbsp;&nbsp;&nbsp;&nbsp; macOS:</strong></summary>


- **After downloading and extracting the file, you must tell macOS that this file is an application.**
1. Open the Terminal app. Type cd followed by a space, then drag the folder containing `SQ_Mac` into the terminal window and press Enter. Run the following command to make `SQ_Mac` executable:
    ```bash
    chmod +x SQ_Mac
    ```
- This command grants **execute permissions** to the `SQ_Mac` file.

2. Run the program. You might need to allow the program to run in your system's  Security & Privacy settings if it was downloaded from an external source. This is a standard macOS security measure.

<p align="center">
<img src="readme_medias\2_macos_download_chmod+x.gif" alt="2_macos_download_chmod+x" width="50%">
<img src="readme_medias\2_mac_os_privacy.png" alt="2_mac_os_privacy" width="32%">
</p>


3. Double-click `SQ_Mac` to start.
    - ⚠️ **Important:** A Terminal window will open to initialize the environment. Do not close this window, or the program will exit. You can simply minimize it.
    - Be Patient: The first startup on macOS can take 1-2 minutes due to Apple's background security verification and package loading. Once the GUI appears, the app is ready for use.


<p align="center">
<img src="readme_medias\2_mac_os_cml_open.png" alt="2_mac_os_cml_open" width="40%">
<img src="readme_medias\2_macos_startup.gif" alt="2_macos_startup" width="48%">
</p>
</details>

</details>


<a id="using-the-source-code"></a>
<details>
<summary style="padding-left: 1em;"><strong>🧑‍💻 Using the Source Code </strong></summary>

- If you choose to run StomataQuant from source, you are probably a power user or developer 😎. 
    > Welcome to explore, **debug, improve, and contribute** to the project!   If you encounter issues or have suggestions, feel free to reach out in the [contact us](#contact-us) section.

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
3. **Run the application using your Python interpreter, and don't forget to download the necessary [model files](#getting-started)**
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
    - Generates feature distribution heatmaps for intuitive visualization of analysis results (as depicted in the following figure).

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
- Select theoperation you want to perform (**AI inference, feature extraction, etc.**), as illustrated on the left;
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

All datasets used for training and validating the **StomataQuant** models are hosted on **Zenodo**. The full dataset repository will be publicly available soon:  : [https://zenodo.org/records/18934358](https://zenodo.org/records/18934358)

<p align="center">
<img src="readme_medias\4_dataset.jpg" alt="4_dataset" width="70%">
</p>

<a id="technical-architecture"></a>
<summary style="font-size:1.5em;font-weight:bold;">🧩 Software Architecture</summary>

- **UI framework**: [PyQt5](https://www.riverbankcomputing.com/static/Docs/PyQt5/)
- **Deep Learning Model Training and Inference**: [YOLOv11 (Ultralytics)](https://github.com/ultralytics/ultralytics)
- **Shape and Data Analysis**:
    - [OpenCV](https://github.com/opencv/opencv)
    - [PIL (Pillow)](https://github.com/python-pillow/Pillow)
    - [NumPy](https://github.com/numpy/numpy)
    - [Shapely](https://github.com/shapely/shapely)
- **Program Acceleration**: [Numba](https://github.com/numba/numba)
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



<a id="citation"></a>
<summary style="font-size:1.5em;font-weight:bold;">📑 Citation</summary>

If you use **StomataQuant** in your research, please cite the following paper:

> Liu, M., Ren, Z., Wei, J., Zhang, H., Li, Y., Wang, G., Xie, P., & Wang, Y.  
**Integrating automated detection and segmentation for quantitative analysis of stomata and pavement cells using StomataQuant.**  *Journal of Plant Ecology.* (Accepted)
<details>
<summary style="padding-left: 1em; cursor: pointer;"><strong>Click to view BibTeX</strong></summary>

```bibtex
@article{StomataQuant,
  title = {Integrating Automated Detection and Segmentation for Quantitative Analysis of Stomata and Pavement Cells using StomataQuant},
  author = {Liu, Meng-Long and Ren, Zi-Rong and Wei, Jian and Zhang, He and Li, Yu-Kang and Wang, Gu-Yan and Xie, Peng and Wang, Yin},
  journal = {Journal of Plant Ecology},
  year = {2026},
  note = {Accepted}
}
```
</details>

<a id="license"></a>
<summary style="font-size:1.5em;font-weight:bold;">📜 License</summary>

- This project uses the **AGPL-3.0 license**. Any derivative works based on this project must:
  - Disclose the complete source code;
  - Include the original copyright notice;
  - Commercial use requires contacting the author for special authorization.


<a id="contact-us"></a>
<summary style="font-size:1.5em;font-weight:bold;">🤝 Contact Us</summary>

- 🌱 Contributions Welcome!
- **StomataQuant** is an independent open-source project developed during academic research.  
    If you are interested in **Plant Phenotyping**, **Computer Vision (YOLO)**, or **PyQt5 GUI development**, contributions of all kinds are warmly welcome.

    - Whether it is **improving performance**, **fixing bugs**, **adding new features**, or **training models for additional plant species**, every contribution is greatly appreciated. Pull requests, suggestions, and discussions are all welcome.

    - Areas where contributions would be especially helpful
        > - **Performance**
        >     - Improve rendering speed when displaying images containing thousands of polygons.
        >     - The current implementation already uses **Numba**, but there is still room for further optimization.
        >
        > - **New AI Models**
        >     - Train and integrate models for additional plant species or different imaging modalities.
        >
        > - **Features**
        >     - Suggestions or implementations of additional features that could improve usability and overall user experience are very welcome.
        >
        > - **Localization (i18n)**
        >     - Help translate the GUI into additional languages.


    - If you find this project useful or have ideas for improvement, please feel free to **open an issue** or **submit a pull request**.    Any contribution is sincerely appreciated.


- Contact:

    - For questions, bug reports, or collaboration inquiries, please contact:
        -  **Menglong Liu**  
            GitHub: https://github.com/Milo-L/  
            Email: milo.liu@stu.pku.edu.cn  

        - **Dr. Yin Wang**  
            Profile: http://scholar.pku.edu.cn/wangyin  
            Email: wangyinpku@pku.edu.cn


---
<p align="center">
<img src="readme_medias\8_bottom.jpg" alt="8_bottom" width="100%">
</p>
