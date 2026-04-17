import sys
import os
leak_path = os.path.join(os.getcwd(), 'leak_deetection')
if leak_path not in sys.path:
    sys.path.insert(0, leak_path)
from predict import batch_predict
print('module', batch_predict.__module__)
print('func', batch_predict)
