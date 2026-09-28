"""Builds KrishiRakshak_Project_Report.docx (template sections: Introduction, Methodology, Process, Results, Discussion)."""
import json
import os
import sys

from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import kb  # noqa: E402

SHOTS = os.path.join(HERE, "screenshots")
ASSETS = os.path.join(HERE, "assets")
PLOTS = os.path.join(ROOT, "ml", "plots")
M = json.load(open(os.path.join(ROOT, "ml", "model", "metrics.json")))
S = json.load(open(os.path.join(HERE, "stats.json"), encoding="utf-8"))
K = S["kpi"]
GREEN = RGBColor(0x14, 0x5A, 0x32)
pct = lambda v: f"{v * 100:.2f}%"

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.3)
sec.top_margin = sec.bottom_margin = Cm(2.2)

st = doc.styles["Normal"]
st.font.name = "Calibri"
st.font.size = Pt(11.5)
st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
st.paragraph_format.space_after = Pt(6)
st.paragraph_format.line_spacing = 1.2
for name, size in (("Heading 1", 18), ("Heading 2", 14), ("Heading 3", 12)):
    h = doc.styles[name]
    h.font.name = "Calibri"; h.font.size = Pt(size); h.font.color.rgb = GREEN; h.font.bold = True
    h.element.rPr.rFonts.set(qn("w:asciiTheme"), "")
    h.paragraph_format.space_before = Pt(14 if name == "Heading 1" else 10)
    h.paragraph_format.space_after = Pt(6)

fig_no = [0]
tab_no = [0]


def para(text, bold=False, italic=False, size=None, align=None, color=None, after=None):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold, r.italic = bold, italic
    if size:
        r.font.size = Pt(size)
    if color:
        r.font.color.rgb = color
    if align is not None:
        p.alignment = align
    if after is not None:
        p.paragraph_format.space_after = Pt(after)
    return p


def rich(parts):
    """parts: list of (text, bold)"""
    p = doc.add_paragraph()
    for t, b in parts:
        r = p.add_run(t); r.bold = b
    return p


def bullet(text, head=None, level=0):
    p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    if head:
        r = p.add_run(head + " "); r.bold = True
    p.add_run(text)
    p.paragraph_format.space_after = Pt(3)
    return p


_num = [0]


def num_reset():
    _num[0] = 0


def numbered(text, head=None):
    _num[0] += 1
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.9)
    p.paragraph_format.first_line_indent = Cm(-0.6)
    p.add_run(f"{_num[0]}. ")
    if head:
        r = p.add_run(head + " "); r.bold = True
    p.add_run(text)
    p.paragraph_format.space_after = Pt(3)


def figure(path, caption, width=16):
    doc.add_picture(path, width=Cm(width))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    fig_no[0] += 1
    c = para(f"Figure {fig_no[0]}: {caption}", italic=True, size=10, align=WD_ALIGN_PARAGRAPH.CENTER, after=10)
    return c


def shade(cell, hex_fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


def table(rows, caption, widths=None, size=10):
    tab_no[0] += 1
    para(f"Table {tab_no[0]}: {caption}", italic=True, size=10, align=WD_ALIGN_PARAGRAPH.CENTER, after=4)
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            cell = t.cell(r, c)
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(v))
            run.font.size = Pt(size)
            run.bold = r == 0
            if r == 0:
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                shade(cell, "145A32")
            elif r % 2 == 0:
                shade(cell, "EEF6F0")
            if widths:
                cell.width = Cm(widths[c])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def page_break():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def toc():
    p = doc.add_paragraph()
    r = p.add_run()
    for tag, txt in (("begin", None), (None, 'TOC \\o "1-2" \\h \\z \\u'), ("separate", None), (None, None), ("end", None)):
        if tag:
            fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), tag); r._r.append(fc)
        elif txt:
            it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = txt; r._r.append(it)
        else:
            t = OxmlElement("w:t"); t.text = "Right-click here and choose “Update Field” to build the table of contents."; r._r.append(t)
    upd = OxmlElement("w:updateFields"); upd.set(qn("w:val"), "true")
    doc.settings.element.append(upd)


def page_numbers():
    p = sec.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run()
    for tag, txt in (("begin", None), (None, "PAGE"), ("end", None)):
        if tag:
            fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), tag); r._r.append(fc)
        else:
            it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = txt; r._r.append(it)
    r.font.size = Pt(9)


# =========================================================== title page
doc.add_picture(os.path.join(ASSETS, "tpl_img0.jpeg"), width=Cm(13))
doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
para("Course: Operating system", size=15, align=WD_ALIGN_PARAGRAPH.CENTER, color=RGBColor(0xFF, 0, 0), after=0)
para("Subject code : 24BTDS145", size=15, align=WD_ALIGN_PARAGRAPH.CENTER, color=RGBColor(0xFF, 0, 0), after=24)
para("PROJECT REPORT", bold=True, size=13, align=WD_ALIGN_PARAGRAPH.CENTER, color=GREEN, after=6)
para("KrishiRakshak: AI-Based Early Detection and Management of Crop Diseases and Pest Infestations",
     bold=True, size=22, align=WD_ALIGN_PARAGRAPH.CENTER, after=10)
para("A farmer- and extension-worker-friendly crop-health surveillance system with image-based diagnosis, "
     "weather-based risk forecasting, pest-trap monitoring, hotspot mapping, expert validation and multilingual advisories",
     italic=True, size=11.5, align=WD_ALIGN_PARAGRAPH.CENTER, after=24)
para("Submitted by", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=4)
t = doc.add_table(rows=5, cols=2)
t.style = "Table Grid"
t.alignment = WD_TABLE_ALIGNMENT.CENTER
for r, (a, b) in enumerate([("Member PRN No", "Name")] + [("24BTDSXXX", "[Member name]")] * 4):
    for c, v in enumerate((a, b)):
        cell = t.cell(r, c); cell.text = ""
        run = cell.paragraphs[0].add_run(v); run.bold = r == 0
        cell.width = Cm(4 if c == 0 else 8)
        if r == 0:
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF); shade(cell, "4472C4")
        else:
            shade(cell, "CFD5EA" if r % 2 else "E9EBF5")
para("", after=18)
para("Joy University", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=0)
para("Academic year 2025–26", align=WD_ALIGN_PARAGRAPH.CENTER)
page_break()

# =========================================================== certificate / abstract
doc.add_heading("Abstract", level=1)
para(f"Plant diseases and insect pests are among the largest causes of crop loss, and in India farmers usually recognise them only "
     f"after visible damage has spread. Extension officers cover large areas and laboratory diagnosis is slow, while the factors that "
     f"drive outbreaks — weather, crop stage, variety, soil and local pest history — are rarely combined into actionable farm-level "
     f"alerts. This project presents KrishiRakshak, a web-based crop-health system that runs in the Chrome browser on desktop and "
     f"mobile. A farmer photographs a diseased leaf and a MobileNetV2 transfer-learning model, trained on {M['n_images']:,} PlantVillage "
     f"images of {M['n_classes']} classes, returns the top-3 diagnoses with confidence. The diagnosis is combined with a 7-day "
     f"weather-based risk forecast from twelve agro-meteorological disease models (e.g. the Hutton criteria for late blight), adjusted "
     f"for crop stage, variety resistance, drainage, irrigation and confirmed cases nearby. Pest-trap counts and IoT sensor readings are "
     f"compared with economic threshold levels. Confirmed cases are clustered with DBSCAN to detect geospatial hotspots and warn "
     f"nearby farms. Every AI diagnosis enters a prioritised validation queue where extension officers confirm, correct or refer it to a "
     f"laboratory; confirmed images are used to retrain the model. Integrated Pest Management advisories — cultural, biological and, "
     f"only as a last resort, chemical control with safe-use instructions — are generated in English, Hindi, Telugu, Tamil, Kannada and Marathi, with "
     f"read-aloud audio. Officials receive a surveillance dashboard. The model achieves {pct(M['test_accuracy'])} accuracy and "
     f"{pct(M['test_top3_accuracy'])} top-3 accuracy on {M['split']['test']:,} unseen test images (macro F1 {M['macro_f1']:.3f}).")
rich([("Keywords: ", True), ("crop disease detection, deep learning, MobileNetV2, transfer learning, integrated pest management, "
                             "disease forecasting, DBSCAN, geospatial surveillance, multilingual advisory, Flask.", False)])
page_break()

doc.add_heading("Table of Contents", level=1)
toc()
page_break()
page_numbers()

# =========================================================== 1. Introduction
doc.add_heading("1. Introduction", level=1)
doc.add_heading("1.1 Context and background", level=2)
para("Agriculture supports a large share of India's population, and crop protection is central to farm income and food security. "
     "The Food and Agriculture Organization estimates that up to 40% of global crop production is lost to plant pests and diseases "
     "every year. Many of these losses are avoidable if a problem is identified early and managed correctly.")
para("In practice, early detection is difficult. Symptoms such as small leaf spots, yellowing or insect eggs are easy to miss, and many "
     "diseases look alike. Village-level extension officers are responsible for thousands of farmers across large areas, and "
     "plant-health laboratories are usually located at district headquarters. As a result, farmers often rely on input dealers or "
     "neighbours for advice, which can lead to wrong diagnoses and unnecessary or excessive pesticide sprays.")
para("At the same time, the information needed to predict outbreaks already exists: weather forecasts, the crop's growth stage, the "
     "variety's resistance, soil drainage and reports of the disease in neighbouring villages. Recent advances in deep learning, "
     "smartphones with good cameras and free weather APIs make it possible to combine these sources into a single decision-support tool.")

doc.add_heading("1.2 Problem statement", level=2)
para("Problem Statement Title: Early detection and management of crop diseases and pest infestations.", bold=True)
para("Farmers often recognise crop diseases or pest infestations only after visible damage has spread. Extension staff may cover "
     "large areas, while laboratory diagnosis and expert advice may not be immediately available. Weather, crop stage, variety, soil "
     "condition and local pest history influence risk, but these inputs are rarely combined into actionable farm-level alerts. "
     "Incorrect diagnosis may lead to delayed treatment, excessive or inappropriate pesticide use, increased cultivation cost, residue "
     "concerns and yield loss. The challenge is to provide timely, reliable and locally relevant detection, forecasting and management support.")
para("Why is this project necessary?", bold=True)
for h, d in [("Late detection:", "damage has already spread by the time symptoms are obvious."),
             ("Limited expert reach:", "few extension staff and laboratories for a very large number of farmers."),
             ("Scattered risk information:", "weather, crop stage, variety, soil and pest history are not combined into alerts."),
             ("Wrong treatment:", "misdiagnosis causes delayed control, wasted money, pesticide residues and resistance."),
             ("No surveillance picture:", "officials lack real-time data to plan preventive interventions."),
             ("Language barrier:", "advice is rarely available in the farmer's own language.")]:
    bullet(d, h)

doc.add_heading("1.3 Objectives and key goals", level=2)
para("The expected solution is a farmer- and extension-worker-friendly crop-health system. The objectives of this project are:")
num_reset()
for h, d in [("Image-based identification:", "diagnose diseases from a leaf photograph using a convolutional neural network."),
             ("Pest-trap and sensor inputs:", "record trap counts and IoT sensor data and raise alerts above the economic threshold level (ETL)."),
             ("Weather-based risk forecasting:", "compute a 7-day disease and pest risk for each farm."),
             ("Geospatial hotspot mapping:", "automatically detect clusters of confirmed cases and warn nearby farms."),
             ("Expert validation:", "let extension officers confirm or correct each AI diagnosis and refer difficult cases to laboratories."),
             ("Multilingual advisories:", "provide Integrated Pest Management (IPM) advice with safe input use in English, Hindi, Telugu, Tamil, Kannada and Marathi."),
             ("Follow-up monitoring:", "schedule re-checks and escalate cases that are not improving."),
             ("Learning from field confirmations:", "retrain the model with expert-confirmed field images."),
             ("Dashboards:", "give agriculture officials surveillance indicators and charts."),
             ("Accessibility:", "run as a website in Chrome on both desktop and mobile phones.")]:
    numbered(d, h)
para("Expected outcomes include earlier detection, reduced crop loss, more targeted pesticide use, faster extension response, improved "
     "surveillance coverage and better planning of preventive interventions.")

doc.add_heading("1.4 Scope of the project", level=2)
para(f"The system covers {len(kb.CROPS)} crops in its risk and pest modules and 14 crops in the image classifier (apple, blueberry, cherry, maize, "
     f"grape, orange, peach, bell pepper, potato, raspberry, soybean, squash, strawberry and tomato). It includes {len(kb.PESTS)} trap-monitored "
     f"pests (fall armyworm, pink bollworm, Helicoverpa, brinjal fruit and shoot borer, yellow stem borer, brown planthopper and whitefly), "
     f"three user roles (farmer, extension officer and administrator/official) and six languages.")

# =========================================================== 2. Literature
doc.add_heading("2. Background and Related Work", level=1)
para("Hughes and Salathé (2015) released PlantVillage, an open dataset of more than 50,000 expertly labelled leaf images. Mohanty et al. "
     "(2016) showed that deep convolutional networks (AlexNet and GoogLeNet) trained on PlantVillage can reach 99.35% accuracy, "
     "but noted that accuracy drops considerably on images taken in different conditions — a key reason why expert validation is "
     "included in this project. MobileNetV2 (Sandler et al., 2018) uses depthwise-separable convolutions and inverted residual blocks, "
     "which makes it about an order of magnitude cheaper than GoogLeNet-class models and suitable for mobile and CPU deployment.")
para("Weather-based disease forecasting has a long history in plant pathology. The Mills table (1944) relates the number of leaf-wet "
     "hours and temperature to apple-scab infection; the Hutton criteria, adopted in the UK in 2017, flag a late-blight risk period when "
     "the minimum temperature is at least 10 °C and relative humidity is at least 90% for six hours or more on two consecutive days. "
     "Integrated Pest Management (IPM) programmes in India use economic threshold levels (ETL) from pheromone-trap catches or field "
     "counts to decide when control is justified.")
para("For spatial surveillance, density-based clustering (DBSCAN; Ester et al., 1996) is widely used to find clusters of events of "
     "arbitrary shape without fixing the number of clusters in advance. Existing mobile apps typically provide either photo "
     "identification or generic advisories; few combine diagnosis, farm-specific forecasting, expert validation, hotspot surveillance "
     "and continual learning in one workflow. This gap motivates KrishiRakshak.")

# =========================================================== 3. Methodology
doc.add_heading("3. Methodology", level=1)
doc.add_heading("3.1 Approach", level=2)
para("The problem was decomposed into three questions a farmer and an officer need answered: What is the problem on this crop? "
     "How likely is it to spread on this farm in the next days? What should be done, safely, and who should check it? The approach "
     "combines three sources of intelligence:")
bullet("a CNN classifier identifies the disease from a leaf image;", "Computer vision —")
bullet("rule-based weather models, adjusted for farm factors and local history, estimate short-term risk;", "Agro-meteorological forecasting —")
bullet("extension officers validate diagnoses, and their decisions feed back into the model and the outbreak map.", "Human expertise —")
para("These are delivered through a three-tier web application (Figure 1): a browser front-end, a Flask server with six "
     "intelligence modules, and a data layer with a SQLite database, model store, knowledge base and external services.")
figure(os.path.join(ASSETS, "architecture.png"), "System architecture of KrishiRakshak")

doc.add_heading("3.2 Tools and technologies", level=2)
table([("Layer", "Technology", "Purpose"),
       ("Front-end", "HTML5, CSS3, JavaScript, Jinja2 templates", "Responsive pages that run in Chrome on desktop and mobile"),
       ("Maps", "Leaflet.js 1.9, OpenStreetMap tiles, Leaflet.heat", "Farm location picker, hotspot map and heatmap"),
       ("Charts", "Chart.js 4", "Weather chart and officials' dashboard"),
       ("Voice", "Web Speech API", "Reads advisories aloud in the selected language"),
       ("Back-end", "Python 3.12, Flask 3", "Routing, authentication, REST APIs, alerts and scheduler"),
       ("Deep learning", "TensorFlow 2.18 / Keras 3, MobileNetV2", "Leaf image classification by transfer learning"),
       ("ML utilities", "scikit-learn, NumPy, Pillow, Matplotlib", "DBSCAN, metrics, image-quality checks, plots"),
       ("Database", "SQLite", "Users, farms, reports, traps, sensors, alerts, model versions"),
       ("Weather", "Open-Meteo forecast API", "Hourly temperature, humidity, rain and wind (past 3 + next 7 days)"),
       ("IoT (simulated)", "/api/sensor endpoint + iot_simulator.py", "Weather-station and smart-trap input")],
      "Technology stack", widths=(3, 5.5, 7.5))
para("Hardware used for development and training: Intel Core i7-10610U laptop CPU (4 cores), 16 GB RAM, no GPU, Windows 11.")

doc.add_heading("3.3 Data collection and sample details", level=2)
doc.add_heading("Image dataset", level=3)
para(f"The PlantVillage dataset (version without augmentation, published on Mendeley Data) was used. It contains {M['n_images']:,} "
     f"colour images of single leaves on uniform backgrounds, in {M['n_classes']} classes: 38 crop–disease or crop–healthy classes of 14 "
     f"crops and one background class (images without leaves). Class sizes range from 152 (potato healthy) to 5,507 (citrus greening) "
     f"images (Figure 2). The data was split with stratified sampling into 70% training ({M['split']['train']:,} images), 15% validation "
     f"({M['split']['val']:,}) and 15% test ({M['split']['test']:,}); the test set was used only once for final evaluation.")
figure(os.path.join(PLOTS, "class_distribution.png"), "Number of images per class in the dataset", width=12)
doc.add_heading("Weather data", level=3)
para("For each farm, hourly temperature, relative humidity, precipitation and wind speed are fetched from the Open-Meteo API for the "
     "past 3 and next 7 days and aggregated into daily minimum/mean/maximum temperature, mean humidity, hours with RH ≥ 90%, "
     "leaf-wetness hours (RH ≥ 90% or rain) and total rain. Results are cached for one hour; if the API is unreachable a seasonal "
     "sample is used and clearly labelled.")
doc.add_heading("Knowledge base", level=3)
para(f"A structured knowledge base was compiled from IPM package-of-practice literature: {len(kb.DISEASES)} disease/health profiles "
     f"(pathogen, symptoms, spread speed, risk model, referral rule and IPM actions with doses and pre-harvest intervals), "
     f"{len(kb.PESTS)} pest profiles with trap type and ETL, {len(kb.CROPS)} crop profiles, and a library of {len(kb.ACTIONS)} IPM action phrases "
     f"translated into six languages. The India-wide ban on agricultural use of streptomycin and tetracycline was respected by "
     f"recommending copper-based bactericides and biological agents for bacterial diseases.")
doc.add_heading("Field and demonstration data", level=3)
para(f"Farm profiles, trap counts, sensor readings and reports are entered through the application. For evaluation, a demonstration "
     f"database was generated with {S['farms']} farms in 32 villages of Maharashtra, Andhra Pradesh, Telangana, Tamil Nadu, Karnataka and Himachal Pradesh, "
     f"{S['reports']} reports over 90 days and {S['traps']:,} trap readings. The images and the AI predictions in these reports are real "
     f"(taken from the validation split and classified by the trained model), while farmers, locations, dates and outbreak clusters are "
     f"synthetic. This allows the dashboard, hotspot and learning features to be evaluated end-to-end.")

# =========================================================== 4. Process
doc.add_heading("4. Process and Implementation", level=1)
doc.add_heading("4.1 Detailed workflow", level=2)
figure(os.path.join(ASSETS, "workflow.png"), "End-to-end workflow from photo capture to continual learning")
num_reset()
for h, d in [("Farm registration:", "the farmer registers a farm with GPS location (map or phone GPS), crop, variety and its resistance, sowing date, area, soil type, drainage and irrigation method."),
             ("Daily risk alerts:", "a background job (every 6 hours) computes the 7-day risk for every farm and creates alerts for high or severe risks; it also creates hotspot and follow-up alerts."),
             ("Photo capture:", "in Chrome the farmer takes or uploads a leaf photo (camera capture on mobile, drag-and-drop on desktop) and selects the farm/crop."),
             ("Quality gate:", "the image is checked for blur and exposure; warnings are shown with the result."),
             ("AI diagnosis:", "the model returns the top-3 classes with confidence; crop-aware re-normalisation is applied and mismatches are flagged."),
             ("Context and advisory:", "the weather risk for the diagnosed disease on that farm is shown, together with the IPM advisory in the farmer's language and a read-aloud button."),
             ("Referral:", "if confidence is below 60%, or the disease is viral/notifiable (e.g. citrus greening), the nearest plant-health laboratory is assigned with directions."),
             ("Expert validation:", "the report enters the officer's queue, prioritised by notifiable disease, not-improving follow-ups, lab need, low confidence and fast spread. The officer confirms or corrects the label, sets severity and adds a note; the farmer is notified."),
             ("Hotspot update:", "confirmed cases are re-clustered and farms with the same crop near a hotspot are alerted."),
             ("Follow-up:", "a re-check is scheduled after 3 days (fast-spreading) or 7 days; outcomes 'same' or 'worse' create another follow-up and 'worse' escalates the case to officers."),
             ("Continual learning:", "confirmed images are stored as labelled examples and used to retrain the classifier."),
             ("Dashboard:", "officials monitor KPIs, trends, districts, AI confidence, follow-up outcomes and trap exceedances.")]:
    numbered(d, h)

doc.add_heading("4.2 AI diagnosis model", level=2)
para("Architecture. Each image is resized to 224×224 pixels and scaled to [−1, 1]. The ImageNet-pretrained MobileNetV2 backbone with "
     "global average pooling produces a 1280-dimensional feature vector. A classification head — Dropout(0.3) → Dense(256, ReLU) → "
     f"Dropout(0.3) → Dense({M['n_classes']}, softmax) — is trained on top.")
para(f"Two-stage training. Because no GPU was available, the frozen backbone was run once over all images to cache their features "
     f"(about 40 minutes at ~23 images/s). The head was then trained with the Adam optimiser (learning rate 10⁻³), batch size 128, "
     f"balanced class weights, early stopping on validation accuracy (patience 8) and learning-rate halving on plateau. Training "
     f"stopped after {M['epochs_run']} epochs and took {M['head_train_seconds']:.0f} seconds. The backbone and head were then joined into a "
     f"single Keras model for inference.")
para("Crop-aware inference. When the farmer selects a crop, the class probabilities are restricted to that crop's classes plus the "
     "background class and re-normalised. If the unrestricted top class belongs to another crop with more than 60% probability, the "
     "farmer is asked to check the selected crop.")
para("Continual learning. When an officer confirms or corrects a report, the stored 1280-d embedding of that image is saved with the "
     "final label. Retraining fine-tunes a copy of the current head for 6 epochs on the original training features plus the field "
     "examples (weighted ×5) at learning rate 2×10⁻⁴. The new head version is activated only if its accuracy on the untouched test set "
     "does not fall by more than 0.5 percentage points, which protects the model against wrong labels. All versions are listed on the "
     "model page.")

doc.add_heading("4.3 Weather-based risk forecasting", level=2)
para("For each disease group, a daily favourability score between 0 and 1 is computed from the aggregated weather. Table 3 lists the "
     "main rules. The farm-level risk for the next seven days uses the highest three-day rolling mean of the daily scores and "
     "combines it with farm factors:")
para("Risk = min(100, 85 × F_weather × F_stage × F_variety × F_environment + min(25, 6 × N_nearby))", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
table([("Model", "Favourable conditions (score 1.0)", "Crops"),
       ("Late blight", "Tmin ≥ 10 °C and ≥ 6 h RH ≥ 90%, Tmean ≤ 26 °C (Hutton criteria)", "Potato, tomato"),
       ("Early blight", "Tmean 20–30 °C and ≥ 8 leaf-wet hours", "Potato, tomato"),
       ("Apple scab", "Wet hours ≥ Mills-table requirement for the temperature (9–14 h)", "Apple"),
       ("Powdery mildew", "Tmean 16–28 °C, RH 50–90%, rain < 2 mm (dry leaves)", "Cherry, squash, grape, apple"),
       ("Rust", "Tmean 15–25 °C and ≥ 6 h RH ≥ 90%", "Maize, soybean, apple"),
       ("Bacterial spot", "Tmean 24–32 °C with ≥ 5 mm splashing rain", "Tomato, pepper, peach, brinjal"),
       ("Black rot", "Tmean 20–32 °C and ≥ 6 wet hours", "Grape, apple"),
       ("Northern leaf blight", "Tmean 18–27 °C and ≥ 6 wet hours", "Maize"),
       ("Gray leaf spot", "Tmean 22–30 °C and ≥ 12 h RH ≥ 90%", "Maize"),
       ("Leaf spots and moulds", "Tmean 20–30 °C and ≥ 8 wet hours", "Tomato, grape, strawberry, rice …"),
       ("Spider mites", "Tmax ≥ 30 °C, RH < 50%, no rain", "Tomato, pepper, brinjal"),
       ("Whitefly/psyllid-borne virus", "Tmean 26–35 °C, RH < 65%, rain < 2 mm", "Tomato, cotton, orange")],
      "Weather favourability rules (partial conditions score 0.45–0.55)", widths=(3.5, 8.5, 4))
table([("Factor", "Values"),
       ("Crop stage (days after sowing ÷ crop duration)", "seedling 0.85 · vegetative 1.0 · flowering/fruiting 1.15 · maturity 0.75 · harvested 0.4"),
       ("Variety resistance", "susceptible 1.0 · moderately resistant 0.75 · resistant 0.5"),
       ("Drainage (humid diseases)", "poor 1.15 · moderate 1.0 · good 0.92"),
       ("Irrigation (humid diseases)", "sprinkler 1.10 · flood 1.03 · rainfed 1.0 · drip 0.93"),
       ("IoT sensor", "leaf wetness ≥ 50% or RH ≥ 90% in the last 24 h adds +0.1 to humid-disease favourability"),
       ("Local history", "+6 per confirmed case (or trap exceedance) within 10 km in 21 days, maximum +25"),
       ("Risk level", "Low < 25 ≤ Moderate < 50 ≤ High < 75 ≤ Severe")],
      "Farm factors used in the risk score", widths=(6, 10))

doc.add_heading("4.4 Pest-trap and sensor module", level=2)
para("Trap readings are normalised to the pest's ETL unit: pheromone-trap counts are divided by the number of traps and the days since "
     "the last check (moths/trap/day or /week); visual counts are averaged per plant or leaf. A value at or above the ETL creates alerts "
     "for the farmer and the officers. IoT weather stations and smart traps post JSON to /api/sensor with a device key; "
     "iot_simulator.py demonstrates this.")
table([("Pest", "Crop(s)", "Monitoring", "ETL used")] +
      [(kb.loc(p["name"], "en"), ", ".join(kb.CROPS[c]["en"] for c in p["crops"]), kb.t("trap.kind." + p["trap"], "en"), f"{p['etl']} {p['unit']}")
       for p in kb.PESTS.values()], "Pests and economic threshold levels (configurable)", widths=(4, 3.5, 4, 4.5))

doc.add_heading("4.5 Hotspot detection", level=2)
para("Reports from the last 30 days that are confirmed or corrected by an officer, or pending with AI confidence ≥ 90%, are grouped by "
     "disease. For each group DBSCAN is run with the haversine metric (ε = 5 km, minimum 3 cases). Each cluster becomes a hotspot with "
     "centroid, radius, case count, cases in the last 7 days and severity (moderate ≥ 3, high ≥ 6, severe ≥ 12 cases or ≥ 6 in the last "
     "week). Farms growing the affected crop within the hotspot radius plus 5 km receive an alert. Farmers see hotspot areas only; "
     "officers also see individual reports, a heatmap and farm-level risk.")

doc.add_heading("4.6 IPM advisory engine and multilingual support", level=2)
para(f"Advisories follow the IPM hierarchy: (1) cultural/field practices, (2) biological control, (3) chemical control only as a "
     f"last resort with product, dose and pre-harvest interval, (4) safe-use instructions (protective equipment, timing, label dose, "
     f"rotation of chemical groups, container disposal), (5) referral and (6) follow-up. Each advisory is composed from the "
     f"{len(kb.ACTIONS)}-phrase action library, so every step is available in all six languages; chemical names and doses are inserted into "
     f"translated templates. The whole user interface ({len(kb.UI['en'])} strings) is translated, and the Web Speech API reads the "
     f"advisory aloud using the browser's Indian-language voices. Officers mark severity; low-severity cases are managed without "
     f"chemical recommendations.")

doc.add_heading("4.7 Database and application structure", level=2)
table([("Table", "Main fields"),
       ("users", "username, password hash, role (farmer/officer/admin), name, phone, district, language"),
       ("farms", "owner, location (lat/lon), village, district, crop, variety, resistance, sowing date, area, soil, drainage, irrigation"),
       ("reports", "image, AI label/confidence/top-3, model version, quality notes, status, final label, severity, officer, referral, lab"),
       ("followups", "report, due date, status, outcome (better/same/worse), note"),
       ("trap_readings", "farm, pest, count, traps, days, normalised value, above-ETL flag, source (manual/sensor)"),
       ("sensor_readings", "farm, device, temperature, humidity, leaf wetness, soil moisture"),
       ("alerts", "user, farm, kind (weather/hotspot/trap/follow-up/validation), level, reference, read flag"),
       ("labs, model_versions", "referral laboratories/KVKs; model version history with accuracy")],
      "Database tables", widths=(3.5, 12.5))
para("The code is organised as app.py (routes and APIs), risk.py (weather and risk models), hotspots.py (DBSCAN), ml_service.py "
     "(inference and retraining), kb/ (knowledge base), i18n/ (translations), templates/ (19 pages) and ml/train.py (training). "
     "Passwords are stored as salted hashes, pages are protected by role, farmers can only see their own farms and reports, and "
     "sensor devices authenticate with a device key.")

doc.add_heading("4.8 Challenges and adaptations", level=2)
table([("Challenge", "Adaptation"),
       ("No GPU on the development laptop", "Cached frozen-backbone features: one CPU pass, then head training and retraining take seconds."),
       ("Strong class imbalance (152–5,507 images)", "Balanced class weights; per-class precision/recall/F1 reported."),
       ("Laboratory images differ from field photos", "Quality gate, crop-aware inference, top-3 display, low-confidence referral, expert validation."),
       ("Translating advice into six languages", "Phrase library with templated doses so new diseases reuse existing translations."),
       ("Weather API outages", "Hourly cache and a clearly labelled seasonal fallback."),
       ("Risk of wrong labels in retraining", "Accept a new model only if held-out accuracy does not drop; keep version history."),
       ("Antibiotic ban for agricultural use", "Copper-based and biological options recommended for bacterial diseases.")],
      "Challenges met during development", widths=(6, 10))

# =========================================================== 5. Results
doc.add_heading("5. Results", level=1)
doc.add_heading("5.1 Model performance", level=2)
table([("Metric", "Value"),
       ("Test accuracy (top-1)", pct(M["test_accuracy"])),
       ("Top-3 accuracy", pct(M["test_top3_accuracy"])),
       ("Macro-averaged F1-score", f"{M['macro_f1']:.4f}"),
       ("Weighted F1-score", f"{M['weighted_f1']:.4f}"),
       ("Test images", f"{M['split']['test']:,}"),
       ("Epochs (early stopping)", str(M["epochs_run"])),
       ("Head training time (CPU)", f"{M['head_train_seconds']:.0f} s"),
       ("Model size (backbone + head)", f"{os.path.getsize(os.path.join(ROOT, 'ml', 'model', 'krishi_model.keras')) / 1e6:.1f} MB")],
      "Classification results on the held-out test set", widths=(8, 5))
figure(os.path.join(PLOTS, "training_curves.png"), "Training and validation accuracy and loss per epoch")
para("Validation accuracy follows training accuracy closely and validation loss does not rise, showing that dropout and early stopping "
     "prevented over-fitting. (Training accuracy is slightly below validation accuracy because dropout is active during training.)")
figure(os.path.join(PLOTS, "confusion_matrix.png"), "Normalised confusion matrix on the test set", width=16)
pc = sorted(M["per_class"].items(), key=lambda kv: kv[1]["f1-score"])
rows = [("Class", "Precision", "Recall", "F1", "Test images")]
for l, v in pc:
    rows.append((kb.full_name(l, "en"), f"{v['precision']:.3f}", f"{v['recall']:.3f}", f"{v['f1-score']:.3f}", int(v["support"])))
table(rows, "Per-class performance, weakest first", widths=(7, 2.2, 2.2, 2.2, 2.4), size=9)
w = pc[:3]
para(f"The weakest classes are {', '.join(kb.full_name(l, 'en') for l, _ in w)}. Most confusions occur between diseases of the same "
     f"crop with similar lesions — for example maize gray leaf spot and northern leaf blight, or tomato target spot, septoria and early "
     f"blight. Because the top-3 list almost always contains the correct class ({pct(M['test_top3_accuracy'])}), the officer can "
     f"quickly correct such cases in the validation screen.")

doc.add_heading("5.2 Application results", level=2)
para("The complete application was run locally and tested in Google Chrome on desktop (1366×900) and at mobile width (390 px). "
     "The following screenshots show the main features.")
for fn, cap in [("01_landing.png", "Landing page with feature overview"),
                ("02_farmer_home.png", "Farmer home: farms with live weather, 7-day risk, alerts and follow-ups"),
                ("03_farm_risk.png", "Farm detail: risk forecast table, weather chart, pest-trap log and IoT sensor readings"),
                ("04_diagnose.png", "Leaf-scan page with camera capture, farm/crop selection and photo tips"),
                ("05_report.png", "Diagnosis result: top-3 predictions, weather-risk link and IPM advisory with read-aloud"),
                ("06_report_kannada.png", "The same result and advisory in Kannada"),
                ("07_advisory_tamil.png", "Advisory page in Tamil"),
                ("09_officer_queue.png", "Extension officer's prioritised validation queue with trap and not-improving panels"),
                ("10_review.png", "Expert review screen: confirm/correct, severity, lab referral and advisory preview"),
                ("11_map.png", "Hotspot map with DBSCAN clusters, report markers and heatmap"),
                ("12_dashboard.png", "Surveillance dashboard for agriculture officials"),
                ("13_model.png", "AI model page: metrics, version history and retraining from field data")]:
    figure(os.path.join(SHOTS, fn), cap, width=15.5)
figure(os.path.join(SHOTS, "08_mobile_home.png"), "Farmer home at mobile-phone width", width=6)

doc.add_heading("5.3 Surveillance indicators (demonstration data)", level=2)
table([("Indicator (last 90 days)", "Value"),
       ("Reports received", K["reports"]), ("Reports with disease/pest", K["diseased"]),
       ("Validated by officers", K["validated"]), ("Pending validation", K["pending"]),
       ("AI–expert agreement", f"{K['agreement']}%"), ("Average validation time", f"{K['avg_response_h']} h"),
       ("Laboratory referrals", K["referrals"]), ("Active hotspots detected", S["hotspots"]),
       ("Village surveillance coverage (30 days)", f"{K['coverage']}%"),
       ("Confirmed cases managed without chemical advice", f"{K['no_chem_pct']}%")],
      "Dashboard indicators computed from the demonstration database", widths=(9, 4))
para(f"The AI–expert agreement ({K['agreement']}%) is measured on the real model predictions for the report images and is consistent with "
     f"the test accuracy. The hotspot module detected {S['hotspots']} hotspots, including every simulated outbreak cluster: " +
     "; ".join(f"{h['name']} ({h['cases']} cases, {', '.join(h['districts'])})" for h in S["hotspot_list"]) + ".")

doc.add_heading("5.4 Comparison with existing standards and approaches", level=2)
table([("Approach", "Accuracy / capability", "Notes"),
       ("Mohanty et al. 2016 – GoogLeNet, fine-tuned", "99.35% (PlantVillage, colour)", "Full fine-tuning on GPU; ~6.8 M parameters"),
       ("Mohanty et al. 2016 – AlexNet, fine-tuned", "~99.3%", "~60 M parameters"),
       ("This project – MobileNetV2 frozen + head", pct(M["test_accuracy"]), "~2.6 M parameters; trained on a laptop CPU; retrains in seconds"),
       ("Manual extension visit", "expert-level", "slow, limited coverage"),
       ("Typical photo-ID apps", "diagnosis only", "no farm-specific forecasting, validation or surveillance")],
      "Comparison with published benchmarks and existing practice", widths=(5.5, 4.5, 6))
para("Our accuracy is a few points below fully fine-tuned networks because the backbone is frozen; in exchange the model is small, "
     "can be trained and retrained on ordinary hardware, and is combined with risk forecasting, expert validation and surveillance "
     "features that single-purpose tools lack.")

# =========================================================== 6. Discussion
doc.add_heading("6. Discussion", level=1)
doc.add_heading("6.1 Interpretation of results", level=2)
for d in [f"A lightweight transfer-learning model reaches {pct(M['test_accuracy'])} accuracy, which is sufficient for a first-line "
          f"screening tool, especially when combined with the top-3 list and expert validation.",
          "Linking the diagnosis to the farm's weather risk turns a label into a decision: the farmer sees whether conditions in the "
          "coming days favour spread and how urgently to act.",
          "Prioritising the officers' queue (notifiable, not improving, lab-needed and low-confidence cases first) makes better use of "
          "scarce extension staff.",
          "Ordering advice by IPM principles, attaching doses and pre-harvest intervals, and making chemical advice depend on severity "
          "supports more targeted pesticide use.",
          "Hotspot alerts give neighbouring farmers an early warning before they see symptoms, which directly addresses the problem "
          "of late detection."]:
    bullet(d)
doc.add_heading("6.2 Limitations", level=2)
for d in ["PlantVillage images are taken on plain backgrounds under controlled conditions. Accuracy on real field photographs with "
          "complex backgrounds is expected to be lower until field images are collected and used for retraining.",
          "The classifier covers 14 crops; important Indian crops such as rice, cotton, chilli, pulses and onion have risk and pest "
          "modules but no image classes yet.",
          "The weather rules are simplified from published models and have not been calibrated against local outbreak records.",
          "Demonstration farms, reports and outbreaks are synthetic, and IoT devices are simulated.",
          "Doses in the knowledge base are indicative and must be checked against product labels and state recommendations.",
          "Live weather and map tiles need an internet connection; very low-literacy users may still need assistance."]:
    bullet(d)
doc.add_heading("6.3 Future work", level=2)
for d in ["Collect and label field images (especially rice, cotton, chilli and pulses) and fine-tune the full network.",
          "Offline Android app with an on-device TensorFlow Lite model for areas with poor connectivity.",
          "SMS, WhatsApp and IVR voice alerts for farmers without smartphones; more Indian languages.",
          "Calibrate risk models with state pest-surveillance and weather-station data; add soil health card inputs.",
          "Integrate real LoRa/GSM smart traps with automatic insect counting by computer vision.",
          "Add satellite (NDVI) crop-stress layers and district-level forecasting of input demand."]:
    bullet(d)

doc.add_heading("7. Conclusion", level=1)
para("KrishiRakshak shows that early detection and management of crop diseases and pests can be supported by a single, easy-to-use web "
     "system that runs in Chrome. It combines image-based symptom identification, pest-trap and sensor inputs, weather-based risk "
     "forecasting, geospatial hotspot mapping, expert validation, multilingual IPM advisories with safe-use guidance, laboratory referral, "
     "follow-up monitoring, learning from field confirmations and dashboards for agriculture officials — every element listed in the "
     "expected solution. With a test accuracy of " + pct(M["test_accuracy"]) + " and an expert-in-the-loop design, the system can help "
     "farmers detect problems earlier, reduce crop loss and unnecessary pesticide use, and help extension services respond faster and "
     "plan preventive interventions.")

doc.add_heading("References", level=1)
num_reset()
for r in ["Hughes, D. P., & Salathé, M. (2015). An open access repository of images on plant health to enable the development of mobile disease diagnostics. arXiv:1511.08060.",
          "Mohanty, S. P., Hughes, D. P., & Salathé, M. (2016). Using deep learning for image-based plant disease detection. Frontiers in Plant Science, 7, 1419.",
          "Sandler, M., Howard, A., Zhu, M., Zhmoginov, A., & Chen, L.-C. (2018). MobileNetV2: Inverted residuals and linear bottlenecks. Proc. IEEE CVPR, 4510–4520.",
          "Ester, M., Kriegel, H.-P., Sander, J., & Xu, X. (1996). A density-based algorithm for discovering clusters in large spatial databases with noise. Proc. KDD-96, 226–231.",
          "Mills, W. D. (1944). Efficient use of sulfur dusts and sprays during rain to control apple scab. Cornell Extension Bulletin 630.",
          "AHDB (2017). Hutton Criteria – late blight risk alerts. Agriculture and Horticulture Development Board, UK.",
          "FAO (2021). Scientific review of the impact of climate change on plant pests. Food and Agriculture Organization of the United Nations, Rome.",
          "Geetharamani, G., & Arun Pandian, J. (2019). Identification of plant leaf diseases using a nine-layer deep convolutional neural network. Computers & Electrical Engineering, 76, 323–338. (PlantVillage dataset on Mendeley Data.)",
          "Open-Meteo (2025). Free weather forecast API. https://open-meteo.com",
          "Directorate of Plant Protection, Quarantine & Storage, Government of India. Integrated Pest Management packages of practices."]:
    numbered(r)

doc.add_heading("Appendix A: How to run the website", level=1)
num_reset()
for d in ["Install Python 3.12 and run: pip install -r requirements.txt",
          "Train the model (downloads nothing else, uses ml/data/plantvillage): python ml/train.py",
          "Create demonstration data: python seed.py",
          "Start the server: python app.py (or double-click run.bat) and open http://localhost:5000 in Google Chrome.",
          "Demo logins are listed in README.md (farmer, officer and admin roles).",
          "Simulate an IoT trap: python iot_simulator.py --farm 1 --pest helicoverpa --count 7"]:
    numbered(d)
doc.add_heading("Appendix B: REST API", level=1)
table([("Endpoint", "Method", "Description"),
       ("/api/sensor", "POST", "IoT weather station / smart trap data (header X-Device-Key)"),
       ("/api/farm/<id>/risk", "GET", "7-day risk forecast for a farm"),
       ("/api/hotspots", "GET", "Current DBSCAN hotspots"),
       ("/api/reports?days=N", "GET", "Geo-referenced reports (officers)"),
       ("/api/farms-risk", "GET", "Top risk for every farm (officers)"),
       ("/api/stats?days=N", "GET", "Dashboard indicators and chart data (officers)")],
      "Application programming interface", widths=(4.5, 2, 9.5))

out = os.path.join(HERE, "KrishiRakshak_Project_Report.docx")
doc.save(out)
print("saved", out)
