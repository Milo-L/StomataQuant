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
- [📜 License](#license)
- [🤝 Contact Us](#contact-us)
---
<a id="overview"></a>
<summary style="font-size:1.5em;font-weight:bold;"> 🌏 Overview </summary>

- **StomataQuant is a graphical user interface software specifically developed for processing and analyzing plant epidermal stomatal images.**
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
   2. or download the [source code](#using-the-source-code) from GitHub.

<a id="using-the-packaged-application"></a>

<details>
<summary style="padding-left: 1em;"><strong>💻 Using the Packaged Application</strong></summary>

1. **Application Download**
    - **Windows**
        + CPU only Application (**Recommended, Most Stable**) | [Download](https://disk.pku.edu.cn/link/AA3E99946022984C9DB11FF430F438B8FA)
        + GPU Application (CUDA Version > 11.6) | [Download](https://disk.pku.edu.cn/link/AA3E99946022984C9DB11FF430F438B8FA)
    - **macOS**
        + CPU only Application | [Download]()

2. **Model Weights Download**

    + **All Models** | [Download]() 
        + **Stomata Detection** | [Download]() 
        + **Stoma and Pore Segmentation** | [Download]() 
        + **Stoma and Pavement Cell Segmentation** | [Download]() 

3. **Before Running the Packaged Application (Preliminary Steps)**
    + **Windows:** After downloading, extract the files to a folder. **Important:** Ensure that the file path contains no special characters or Chinese characters.
        + Click the executable file to run the application.

    + **macOS:** After downloading, you need to make the application executable.
        + Open Terminal and navigate to the downloaded directory, then run the command: `chmod +x <application_name>` (replace `<application_name>` with the actual application file name).
</details>


<a id="using-the-source-code"></a>
<details>
<summary style="padding-left: 1em;"><strong>🧑‍💻 Using the Source Code </strong></summary>

1. **Clone the repository**
    ```
    git clone [https://github.com/Milo-L/Stomata-Quant.git](https://github.com/Milo-L/Stomata-Quant.git)
    ```
2. **Install dependencies**
    ```
    pip install -r requirements.txt
    ```
3. **Run the application by your python interpreter**
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
    - Integrates YOLO objective detection and segmentation models for automated stomata detection and stoma, pore and pavement cell segmentation.
2. **Result Editing Capability:** 
    - Allows for manual verification and editing of AI inference outcomes.
3. **Measurement and Analysis:**
    - Extraction of shape features (e.g., count, area, perimeter and so on), with the specific features available varying depending on the shape type.
4. **Comprehensive Annotation Tools and Management:**
    - Offers a variety of manual annotation tools, including polygons, rectangles, rotated rectangles, lines, and points, with integrated support for importing and exporting these annotation types.
5. **Batch Processing Capability:** 
    - Allows for automated execution of model inference and analysis tasks on multiple loaded images.
6. **Heatmap Generation:** 
    - Generates feature distribution heatmaps for intuitive visualization of analysis results (as depicted in follwing figure ).

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
    - Focus on the number or distribution of stomata / measure stomatal density:
        - → Select `stomata detection model`
        - The inference result is **rectangle** for the potential stomatal complex
    - Focus on stomatal/pore size / measure stomatal aperture or size:
        - → Select `stoma and pore segmentation model`
        - The inference result is **polygon** for the potential stoma and its pore
    - Focus on pavement cell / measure stomatal index, pavement cell shape descriptor:
        - → Select `stoma and pavement cell segmentation model`
        - The inference result is **polygon** for the potential stomatal complex and pavement cell
</details>

<details>
<summary style="padding-left: 1.5em;"><strong>03. AI Inference</strong></summary>

- Click `AI😎` button → Run inference to execute automatic detection or segementation
- Inference results will be directly displayed on the image as shown in following figures

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
3. The results will be displayed in the right-side `ResultsSummary` and `MeasuredResults` sub-windows
4. You can choose to copy or export the results to a CSV file

<p align="center">
<img src="readme_medias\3_getfeature1.jpg" alt="3_getfeature1" width="32%">
<img src="readme_medias\3_getfeature2.jpg" alt="3_getfeature2" width="32%">
<img src="readme_medias\3_getfeature3.jpg" alt="3_getfeature3" width="32%">
</p>
</details>

<details>
<summary style="padding-left: 1.5em;"><strong>Workflow Summmary</strong></summary>
<p align="center">
<img src="readme_medias\3_workflow.jpg" alt="3_workflow" width="70%">
</p>
</details>




<a id="common_usage_scenarios"></a>

<summary style="padding-left: 1em;"><strong>🕵️ Common usage scenarios</strong></summary>

<details>
<summary style="padding-left: 1.5em;"><strong>Rapid measurement of stomatal aperture or size</strong></summary>

- If you want to **measure stomatal aperture or size** and quickly edit inference results:
    1. you can use the `GetMER` button after model inference to obtain the minimum bounding rotated rectangle of the polygons;
    2. You can set the polygons to be invisible and only display the rotated rectangles for quick editing;
    3. After editing, click `Feature Extraction` to quickly obtain stomatal aperture and size data.

<p align="center">
<img src="readme_medias\3_rapid_stomatal_apeature.gif" alt="3_rapid_stomatal_apeature" width="70%">
</p>
</details>

<details>
<summary style="padding-left: 1.5em;"><strong>Rapid measurement of stomatal index</strong></summary>

- If you want to quickly **measure the stomatal index** and edit the inference results, you can use `Analyze`→ `Shape Filter` to select the shapes you want to filter out that are located on certain edges after model inference;
- Then you can use `View`→`All shapes are displayed as points` to replace each shape (represent a cell) with a point;
- Next confirm and count the cells by adding or deleting points;
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

<details>
<a id="shape-editing"></a>
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

<details>
<a id="train-a-new-model"></a>
<summary style="padding-left: 1.5em;"><strong>Training New Models and Contributing</strong></summary>

- To train a new model or fine-tune an existing one, please refer to the official [Ultralytics training documentation](https://docs.ultralytics.com/modes/train/), which offers comprehensive guidance on dataset preparation, training parameter configuration, and the training process itself.

- **If you're interested in contributing to StomataQuant, you can prepare annotated datasets and [contact us](#contact-us). We plan to release next-generation models for community use in the future.**
</details>

---
<a id="dataset-used-for-training-the-model"></a>
<summary style="font-size:1.5em;font-weight:bold;">📖 Dataset used for training the model</summary>

- Dataset for the stomata dectection model | [Download]()
- Dataset for the stoma and pore segemetation model | [Download]()
- Dataset for the stoma and pavement cell segmentaion model | [Download]()
<p align="center">
<img src="readme_medias\4_dataset.jpg" alt="4_dataset" width="40%">
</p>


<a id="technical-architecture"></a>
<summary style="font-size:1.5em;font-weight:bold;">🧩 Software Architecture</summary>

- **UI framwork**: [PyQt5](https://www.riverbankcomputing.com/static/Docs/PyQt5/)
- **Deep Learning Model Training and  Inference**: [YOLOv11 (Ultralytics)](https://github.com/ultralytics/ultralytics)
- **Shape and Data Analysis**:
    - [OpenCV](https://github.com/opencv/opencv)
    - [PIL (Pillow)](https://github.com/python-pillow/Pillow)
    - [NumPy](https://github.com/numpy/numpy)
    - [shapely](https://github.com/shapely/shapely)
- **Program Acceleration**: [numba](https://github.com/numba/numba)
- **Heatmap Visualization**: [Matplotlib](https://github.com/matplotlib/matplotlib)


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
