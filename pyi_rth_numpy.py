"""
PyInstaller runtime hook for numpy
Prevents the "CPU dispatcher tracer already initialized" error
"""
import os
import sys

# Set environment variable to disable numpy's CPU dispatcher tracing
os.environ['NUMPY_EXPERIMENTAL_ARRAY_FUNCTION'] = '0'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
