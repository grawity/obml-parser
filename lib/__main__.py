def main():
    import argparse
    import glob
    import sys

    from .process import process_one_file

    parser = argparse.ArgumentParser()
    parser.add_argument("obml_file", nargs="*")
    args = parser.parse_args()

    if not args.obml_file:
        args.obml_file = glob.glob("*.obml*")

    if not args.obml_file:
        exit("obml-parser: No files specified.")

    for arg in args.obml_file:
        process_one_file(arg)

if __name__ == "__main__":
    main()
