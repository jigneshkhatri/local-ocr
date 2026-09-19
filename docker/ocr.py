import argparse
import sys
from pathlib import Path

from pipeline import create_pipeline, find_pdfs, process_pdf


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run PP-StructureV3 on PDF files."
    )

    parser.add_argument(
        "--input",
        required=True,
        help="PDF file or directory containing PDFs.",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Output directory.",
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively search for PDFs.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    pdfs = find_pdfs(
        input_path,
        args.recursive,
    )

    if not pdfs:
        print("No PDF files found.")
        return 0

    output_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(f"Found {len(pdfs)} PDF(s).")

    pipeline = create_pipeline()

    successful = 0
    failed = 0

    for pdf in pdfs:
        if process_pdf(
            pipeline,
            pdf,
            output_path,
        ):
            successful += 1
        else:
            failed += 1

    print("\nProcessing complete.")
    print(f"Successful: {successful}")
    print(f"Failed:     {failed}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
