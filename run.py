"""Entry point: python run.py [file.pdf]"""
import multiprocessing

if __name__ == "__main__":
    # In the packaged .exe each page-drawing process is another start of this program; freeze_support() turns
    # it into the drawing process right here, before the window's code is imported (it doesn't need any of it).
    multiprocessing.freeze_support()
    from aerialist.main import main
    main()
