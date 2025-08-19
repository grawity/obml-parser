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

    for arg in args.obml_file:
        process_one_file(arg)
