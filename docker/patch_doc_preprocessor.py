from pathlib import Path
import sys
import yaml


TARGETS = {
    "PP-LCNet_x1_0_doc_ori": "/models/PP-LCNet_x1_0_doc_ori",
    "UVDoc": "/models/UVDoc",
}


def patch_node(node, changes):
    if isinstance(node, dict):
        model_name = node.get("model_name")

        if model_name in TARGETS:
            old = node.get("model_dir")
            node["model_dir"] = TARGETS[model_name]
            changes.append(
                f"{model_name}: {old!r} -> {TARGETS[model_name]!r}"
            )

        for value in node.values():
            patch_node(value, changes)

    elif isinstance(node, list):
        for item in node:
            patch_node(item, changes)


def main():
    config_root = Path(
        "/usr/local/lib/python3.10/dist-packages/paddlex/configs"
    )

    candidates = list(config_root.rglob("*.yaml"))
    candidates += list(config_root.rglob("*.yml"))

    matches = []

    for path in candidates:
        try:
            text = path.read_text()
        except Exception:
            continue

        if "pipeline_name: doc_preprocessor" in text:
            matches.append(path)

    if not matches:
        print("ERROR: Could not find doc_preprocessor configuration.")
        sys.exit(1)

    print("Found doc_preprocessor configuration(s):")
    for path in matches:
        print(f"  {path}")

    patched_any = False

    for path in matches:
        with path.open("r") as f:
            config = yaml.safe_load(f)

        changes = []
        patch_node(config, changes)

        if changes:
            with path.open("w") as f:
                yaml.safe_dump(
                    config,
                    f,
                    sort_keys=False,
                    default_flow_style=False,
                )

            print(f"\nPatched: {path}")
            for change in changes:
                print(f"  {change}")

            patched_any = True

    if not patched_any:
        print(
            "ERROR: Found doc_preprocessor config, "
            "but none of the expected models were present."
        )
        sys.exit(1)

    print("\nDocPreprocessor patch completed successfully.")


if __name__ == "__main__":
    main()