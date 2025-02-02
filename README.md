#  BLIP: Bayesian LISA Pipeline



This is a bayesian pipeline for detecting stochastic backgrounds with LISA. BLIP stands for Bayesian LIsa Pipeline fully written in python


1) It is easier to maintain and run python code in virtual environments. Make a new virtualenv by doing

`python3 -m venv lisaenv`

2) Source it on linux or Mac by doing

`source lisaenv/bin/activate`

For Windows, source it by 

`activate`  while in `\lisawork\Scripts`


3) We need numpy, scipy, astropy, and sympy for running this and matplotlib and chainconsumer are required for plotting. Install them all by doing

`pip install numpy scipy astropy sympy matplotlib chainconsumer`

4) We also need the healpy, the skymap package

`pip install healpy`

5) The sampler [dynesty](https://dynesty.readthedocs.io/en/latest/) is used for nested sampling. We get both the posteriors and bayesian evidence from it. The latter is the detection statistic. Install dynesty by doing

`pip install dynesty`

6) Some functionality also needs cython

`pip install cython`

7) You can change the parameters and the signal model in params.ini

To run do `python run_blip.py params.ini`

Posterior plots are automatically made in the output directory specified in params.ini


8) If you want to generate local documentation pages you also need sphinx

`pip install sphinx`

**Note**: The code is setup to work with python 3 and might not work with python2
More documentation at https://blip.readthedocs.io/en/latest/

## Conda Installation

1) Conda is a common python virtual environment manager. If you already have conda, start at step 2; otherwise [install conda](https://docs.conda.io/projects/conda/en/latest/user-guide/install/) or use the method above.

2) Create an environment. Chainconsumer (at time of writing) only works with python 3.6 or earlier, so we'll specify python 3.6.

`conda create --name lisawork python=3.6`

3) Activate it by

`conda activate lisawork`

4) You will likely need to add the conda-forge channel to install some packages:

`conda config --add channels conda-forge`

5) We need numpy, scipy, sympy, and astropy for running this; matplotlib is required for plotting. Install them all by doing

`conda install numpy scipy astropy sympy matplotlib`

6) Chainconsumer is also needed for plotting but needs to be installed by doing

`conda install -c samreay chainconsumer`

7) We also need the healpy, the skymap package

`conda install healpy`

8) The sampler [dynesty](https://dynesty.readthedocs.io/en/latest/) is used for nested sampling. We get both the posteriors and bayesian evidence from it. The latter is the detection statistic. Install dynesty by doing

`conda install dynesty`

9) Some functionality also needs cython

`conda install cython`

10) You can change the parameters and the signal model in params.ini

To run do `python run_blip.py params.ini`

Posterior plots are automatically made in the output directory specified in params.ini
