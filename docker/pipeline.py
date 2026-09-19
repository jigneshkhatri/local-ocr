import sys
from pathlib import Path

from paddleocr import PPStructureV3


MODEL_DIR = Path("/models")


def find_pdfs(path: Path, recursive: bool):
    if path.is_file():
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"Input file is not a PDF: {path}")

        return [path]

    if path.is_dir():
        pattern = "**/*.pdf" if recursive else "*.pdf"

        return sorted(
            p for p in path.glob(pattern)
            if p.is_file()
        )

    raise FileNotFoundError(
        f"Input path does not exist: {path}"
    )


def model_path(name: str) -> str:
    path = MODEL_DIR / name

    if not path.is_dir():
        raise RuntimeError(
            f"Required model directory does not exist: {path}"
        )

    return str(path)


def create_pipeline():
    print("Initializing PP-StructureV3...")

    pipeline = PPStructureV3(

        # ----------------------------------------------------
        # Layout
        # ----------------------------------------------------

        layout_detection_model_dir=model_path(
            "PP-DocLayout_plus-L"
        ),

        region_detection_model_dir=model_path(
            "PP-DocBlockLayout"
        ),

        # ----------------------------------------------------
        # Document preprocessing
        #
        # Keep BOTH enabled.
        # ----------------------------------------------------

        doc_orientation_classify_model_dir=model_path(
            "PP-LCNet_x1_0_doc_ori"
        ),

        doc_unwarping_model_dir=model_path(
            "UVDoc"
        ),

        use_doc_orientation_classify=True,
        use_doc_unwarping=True,

        # ----------------------------------------------------
        # OCR
        # ----------------------------------------------------

        text_detection_model_dir=model_path(
            "PP-OCRv5_server_det"
        ),

        text_recognition_model_dir=model_path(
            "PP-OCRv5_server_rec"
        ),

        textline_orientation_model_dir=model_path(
            "PP-LCNet_x1_0_textline_ori"
        ),

        use_textline_orientation=True,

        # ----------------------------------------------------
        # Tables
        # ----------------------------------------------------

        table_classification_model_dir=model_path(
            "PP-LCNet_x1_0_table_cls"
        ),

        wired_table_cells_detection_model_dir=model_path(
            "RT-DETR-L_wired_table_cell_det"
        ),

        wireless_table_cells_detection_model_dir=model_path(
            "RT-DETR-L_wireless_table_cell_det"
        ),

        wired_table_structure_recognition_model_dir=model_path(
            "SLANeXt_wired"
        ),

        wireless_table_structure_recognition_model_dir=model_path(
            "SLANet_plus"
        ),

        # ----------------------------------------------------
        # Formula
        # ----------------------------------------------------

        formula_recognition_model_dir=model_path(
            "PP-FormulaNet_plus-L"
        ),
    )

    print("PP-StructureV3 initialized.")

    return pipeline


def process_pdf(pipeline, pdf: Path, output_path: Path):
    print(f"\nProcessing: {pdf}")

    pdf_output = output_path / pdf.stem
    pdf_output.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        results = pipeline.predict(
            input=str(pdf)
        )

        for page_index, result in enumerate(results, start=1):
            print(
                f"  Saving page/result {page_index}"
            )

            result.save_to_json(
                save_path=str(pdf_output)
            )

            result.save_to_markdown(
                save_path=str(pdf_output)
            )

        print("  Done.")
        return True

    except Exception as exc:
        print(
            f"  ERROR processing {pdf}: {exc}",
            file=sys.stderr,
        )
        return False
