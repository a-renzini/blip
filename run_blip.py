import pickle
import numpy as np
import sys, configparser, subprocess
from src.makeLISAdata import LISAdata
from src.models import Model, Injection
from tools.plotmaker import plotmaker
from tools.plotmaker import mapmaker
from tools.plotmaker import fitmaker
import matplotlib.pyplot as plt
from multiprocessing import Pool
import time

class LISA(LISAdata, Model):

    '''
    Generic class for getting data and setting up the prior space
    and likelihood. This is tuned for ISGWB analysis at the moment
    but it should not be difficult to modify for other use cases.
    '''

    def __init__(self,  params, inj):

        # set up the LISAdata class
        LISAdata.__init__(self, params, inj)

        # Generate or get mldc data
        if self.params['mldc']:
            self.read_mldc_data()
        else:
            self.makedata()

        # Set up the Bayes class
        print("Building Bayesian model...")
        self.make_data_correlation_matrix()
        self.Model = Model(params,inj,self.fdata,self.f0,self.tsegmid,self.rmat)

        # Make some simple diagnostic plots to contrast spectra
        if self.params['mldc']:
            self.plot_spectra()
        else:
            self.diag_spectra()
        
        ## save the Model and Injection as needed
        with open(params['out_dir'] + '/model.pickle', 'wb') as outfile:
            pickle.dump(self.Model, outfile)
        
        if not params['mldc']:
            with open(params['out_dir'] + '/injection.pickle', 'wb') as outfile:
                pickle.dump(self.Injection, outfile)
            

    def makedata(self):

        '''
        Just a wrapper function to use the methods the LISAdata class
        to generate data. Return Frequency domain data.
        '''

        ## define the splice segment duration
        tsplice = 1e4
        ## the segments to be splices are half-overlapping
        nsplice = 2*int(self.params['dur']/tsplice) + 1
        ## arrays of segmnent start and mid times
        tsegmid = self.params['tstart'] +  (tsplice/2.0) * np.arange(nsplice) + (tsplice/2.0)
        ## Number of time-domain points in a splice segment
        Npersplice = int(self.params['fs']*tsplice)
        ## leave out f = 0
        frange = np.fft.rfftfreq(Npersplice, 1.0/self.params['fs'])[1:]
        ## the charecteristic frequency of LISA, and the scaled frequency array
        fstar = 3e8/(2*np.pi*self.armlength)
        f0 = frange/(2*fstar)
        
        ## Build the Injection object
        print("Constructing injection...")
        self.Injection = Injection(self.params,self.inj,frange,f0,tsegmid)
        
        ## assign a couple additional universal injection attributes needed in add_sgwb_data()
        self.Injection.Npersplice = Npersplice
        self.Injection.nsplice = nsplice
        
        # Generate TDI noise
        times, self.h1, self.h2, self.h3 = self.Injection.components['noise'].gen_noise_spectrum()
        delt = times[1] - times[0]

        # Cut to required size
        N = int((self.params['dur'])/delt)
        self.h1, self.h2, self.h3 = self.h1[0:N], self.h2[0:N], self.h3[0:N]

        ## create time-domain contribution from each injection component that isn't noise
        for component in self.Injection.sgwb_component_names:
            h1_gw, h2_gw, h3_gw, times = self.add_sgwb_data(self.Injection.components[component])
            h1_gw, h2_gw, h3_gw = h1_gw[0:N], h2_gw[0:N], h3_gw[0:N]

            # Add gravitational-wave time series to noise time-series
            self.h1 = self.h1 + h1_gw
            self.h2 = self.h2 + h2_gw
            self.h3 = self.h3 + h3_gw
        

        self.timearray = times[0:N]
        if delt != (times[1] - times[0]):
            raise ValueError('The noise and signal arrays are at different sampling frequencies!')

        # Desample if we increased the sample rate for time-shifts.
        if self.params['fs'] != 1.0/delt:
            self.params['fs'] = 1.0/delt

        # Generate lisa freq domain data from time domain data
        self.r1, self.r2, self.r3, self.fdata, self.tsegstart, self.tsegmid = self.tser2fser(self.h1, self.h2, self.h3, self.timearray)

        # Charactersitic frequency. Define f0
        cspeed = 3e8
        fstar = cspeed/(2*np.pi*self.armlength)
        self.f0 = self.fdata/(2*fstar)
        
    def make_data_correlation_matrix(self):
        '''
        Uses the generated time-domain data series to construct a data correlation matrix.
        
        Used to be the initialization of the (now defunct) likelihoods.py
        '''
        self.r12 = np.conj(self.r1)*self.r2
        self.r13 = np.conj(self.r1)*self.r3
        self.r21 = np.conj(self.r2)*self.r1
        self.r23 = np.conj(self.r2)*self.r3
        self.r31 = np.conj(self.r3)*self.r1
        self.r32 = np.conj(self.r3)*self.r2
        self.rbar = np.stack((self.r1, self.r2, self.r3), axis=2)

        ## create a data correlation matrix
        self.rmat = np.zeros((self.rbar.shape[0], self.rbar.shape[1], self.rbar.shape[2], self.rbar.shape[2]), dtype='complex')

        for ii in range(self.rbar.shape[0]):
            for jj in range(self.rbar.shape[1]):
                self.rmat[ii, jj, :, :] = np.tensordot(np.conj(self.rbar[ii, jj, :]), self.rbar[ii, jj, :], axes=0 )
    
    def read_mldc_data(self):
        '''
        Just a wrapper function to use the methods the LISAdata class to
        read data. Return frequency domain data. Since this was used
        primarily for the MLDC, this assumes that the data is doppler
        tracking and converts to strain data.
        '''

        h1, h2, h3, self.timearray = self.read_data()

        # Calculate other tdi combinations if necessary.
        if self.params['tdi_lev'] == 'aet':
            h1 = (1.0/3.0)*(2*h1 - h2 - h3)
            h2 = (1.0/np.sqrt(3.0))*(h3 - h2)
            h3 = (1.0/3.0)*(h1 + h2 + h3)

        # Generate lisa freq domain data from time domain data
        self.r1, self.r2, self.r3, self.fdata, self.tsegstart, self.tsegmid = self.tser2fser(h1, h2, h3, self.timearray)

        # Charactersitic frequency. Define f0
        cspeed = 3e8
        fstar = cspeed/(2*np.pi*self.armlength)
        self.f0 = self.fdata/(2*fstar)

        # Convert doppler data to strain if readfile datatype is doppler.
        if self.params['datatype'] == 'doppler':

            # This is needed to convert from doppler data to strain data.
            self.r1, self.r2, self.r3 = self.r1/(4*self.f0.reshape(self.f0.size, 1)), self.r2/(4*self.f0.reshape(self.f0.size, 1)), self.r3/(4*self.f0.reshape(self.f0.size, 1))

        elif self.params['datatype'] == 'strain':
            pass


    def diag_spectra(self):

        '''
        A function to do simple diagnostics. Plot the expected spectra and data.
        '''

        # ------------ Calculate PSD ------------------

        # PSD from the FFTs
        data_PSD1, data_PSD2, data_PSD3  = np.mean(np.abs(self.r1)**2, axis=1), np.mean(np.abs(self.r2)**2, axis=1), np.mean(np.abs(self.r3)**2, axis=1)

        # "Cut" to desired frequencies
        idx = np.logical_and(self.fdata >=  self.params['fmin'] , self.fdata <=  self.params['fmax'])
        psdfreqs = self.fdata[idx]

        #Charactersitic frequency
        fstar = 3e8/(2*np.pi*self.armlength)

        # define f0 = f/2f*
        f0 = self.fdata/(2*fstar)

        # Get desired frequencies for the PSD
        # We want to normalize PSDs to account for the windowing
        # Also convert from doppler-shift spectra to strain spectra
        data_PSD1,data_PSD2, data_PSD3 = data_PSD1[idx], data_PSD2[idx], data_PSD3[idx]

        # The last two elements are the position and the acceleration noise levels.
        Np, Na = 10**self.inj['log_Np'], 10**self.inj['log_Na']

        # Modelled Noise PSD
        C_noise = self.Injection.components['noise'].instr_noise_spectrum(self.fdata,self.f0, Np, Na)

        # Extract noise auto-power
        S1, S2, S3 = C_noise[0, 0, :], C_noise[1, 1, :], C_noise[2, 2, :]
        
        ## need to generate the population response at the data frequencies
        ## we can't do this earlier because we need the data time array
        if 'population' in self.Injection.sgwb_component_names:
            ## just use the analysis response if the lmax are the same (or there is no sph component)
            if not self.params['sph_flag'] and not self.inj['sph_flag']:
                ## grab a random isotropic response
                sm_name = [name for name in self.Model.submodel_names if name!='noise'][0]
                response_mat = self.Model.submodels[sm_name].response_mat
                self.Injection.components['population'].inj_response_mat_true = response_mat
            elif self.params['sph_flag'] and self.inj['sph_flag'] and self.inj['inj_lmax']==self.params['lmax']:
                ## grab a random anisotropic response
                sm_name = [name for name in self.Model.submodel_names if (name!='noise' and self.Model.submodels[name].has_map)][0]
                response_mat = self.Model.submodels[sm_name].response_mat
                self.Injection.components['population'].inj_response_mat_true = np.einsum('ijklm,m', response_mat, self.Injection.components['population'].alms_inj)
            else:
                inj_response_mat_true = self.Injection.components['population'].response(f0,self.tsegmid,**self.Injection.components['population'].response_kwargs)
                if hasattr(self.Injection.components['population'],'has_map') and self.Injection.components['population'].has_map:
                    self.Injection.components['population'].inj_response_mat_true = np.einsum('ijklm,m', inj_response_mat_true, self.Injection.components['population'].alms_inj)
                else:
                    self.Injection.components['population'].inj_response_mat_true = inj_response_mat_true

            
        
        
        plt.close()
        ymins = []
        for component_name in self.Injection.sgwb_component_names:
            S1_gw = self.Injection.plot_injected_spectra(component_name,fs_new=self.fdata,convolved=True,legend=True,channels='11',return_PSD=True,lw=0.75,color=self.Injection.components[component_name].color)
            ymins.append(S1_gw.min())
            S2_gw, S3_gw = self.Injection.compute_convolved_spectra(component_name,fs_new=self.fdata,channels='22'), self.Injection.compute_convolved_spectra(component_name,fs_new=self.fdata,channels='33')
            S1, S2, S3 = S1+S1_gw, S2+S2_gw, S3+S3_gw
       
            plt.loglog(self.fdata, S1, label='Simulated Total spectrum', lw=0.75,color='cadetblue')


        # noise budget plot
        plt.loglog(psdfreqs, data_PSD3,label='PSD, data series', alpha=0.6, lw=0.75,color='slategrey')
        plt.loglog(self.fdata, C_noise[2, 2, :], label='Simulated instrumental noise spectrum', lw=0.75,color='dimgrey')
        
        ## avoid plot squishing due to signal spectra with cutoffs, etc.
        ymin = np.min(ymins)
        if ymin < 1e-43:
            plt.ylim(bottom=1e-43)
        
        plt.legend()
        plt.xlabel('$f$ in Hz')
        plt.ylabel('PSD 1/Hz ')
        plt.xlim(0.5*self.params['fmin'], 2*self.params['fmax'])
        plt.savefig(self.params['out_dir'] + '/psd_budget.png', dpi=200)
        print('Diagnostic spectra plot made in ' + self.params['out_dir'] + '/psd_budget.png')
        plt.close()


        plt.loglog(self.fdata, S3, label='required',color='mediumvioletred')
        plt.loglog(psdfreqs, data_PSD3,label='PSD, data', alpha=0.6,color='slategrey')
        plt.xlabel('$f$ in Hz')
        plt.ylabel('PSD 1/Hz ')
        plt.legend()
        plt.grid(linestyle=':',linewidth=0.5 )
        plt.xlim(0.5*self.params['fmin'], 2*self.params['fmax'])

        plt.savefig(self.params['out_dir'] + '/diag_psd.png', dpi=200)
        print('Diagnostic spectra plot made in ' + self.params['out_dir'] + '/diag_psd.png')
        plt.close()




        ## lets also plot psd residue.
        rel_res_mean = (data_PSD3 - S3)/S3

        plt.semilogx(self.fdata, rel_res_mean , label='relative mean residue',color='slategrey')
        plt.xlabel('f in Hz')
        plt.ylabel(' Rel. residue')
        plt.ylim([-1.50, 1.50])
        plt.legend()
        plt.grid()
        plt.xlim(0.5*self.params['fmin'], 2*self.params['fmax'])

        plt.savefig(self.params['out_dir'] + '/res_psd.png', dpi=200)
        print('Residue spectra plot made in ' + self.params['out_dir'] + '/res_psd.png')
        plt.close()
        
        # cross-power diag plots. We will only do 12. IF TDI=XYZ this is S_XY and if TDI=AET
        # this will be S_AE
        
        ii, jj = 2,0
        IJ = str(ii+1)+str(jj+1)
        
        Sx = C_noise[ii,jj,:]
        
        ymins = []
        iymins = []
        for component_name in self.Injection.sgwb_component_names:
            if component_name != 'noise':
                Sx_gw = self.Injection.compute_convolved_spectra(component_name,fs_new=self.fdata,channels=IJ) + self.Injection.compute_convolved_spectra(component_name,fs_new=self.fdata,channels=IJ,imaginary=True)
                ymins.append(np.real(Sx_gw).min())
                iymins.append(np.imag(Sx_gw).min())
                Sx = Sx + Sx_gw
       
        CSDx = np.mean(np.conj(self.rbar[:, :, ii]) * self.rbar[:, :, jj], axis=1)

        plt.subplot(2, 1, 1)
        if len(Sx.shape) == 1:
            plt.loglog(self.fdata, np.abs(np.real(Sx)), label='Re(Required ' + str(ii+1) + str(jj+1) + ')',color='mediumvioletred')
        else:
            plt.loglog(self.fdata, np.mean(np.abs(np.real(Sx)),axis=1), label='Re(Required ' + str(ii+1) + str(jj+1) + ')',color='mediumvioletred')
        plt.loglog(psdfreqs, np.abs(np.real(CSDx)) ,label='Re(CSD' + str(ii+1) + str(jj+1) + ')', alpha=0.6,color='slategrey')
        plt.xlabel('f in Hz')
        plt.ylabel('Power in 1/Hz')
        plt.legend()
        plt.ylim([1e-44, 5e-40])
        plt.xlim(0.5*self.params['fmin'], 2*self.params['fmax'])
        plt.grid()

        plt.subplot(2, 1, 2)
        if len(Sx.shape) == 1:
            plt.loglog(self.fdata, np.abs(np.imag(Sx)), label='Im(Required ' + str(ii+1) + str(jj+1) + ')',color='mediumvioletred')
        else:
            plt.loglog(self.fdata, np.mean(np.abs(np.imag(Sx)),axis=1), label='Im(Required ' + str(ii+1) + str(jj+1) + ')',color='mediumvioletred')
        plt.loglog(psdfreqs, np.abs(np.imag(CSDx)) ,label='Im(CSD' + str(ii+1) + str(jj+1) + ')', alpha=0.6,color='slategrey')
        plt.xlabel('f in Hz')
        plt.ylabel(' Power in 1/Hz')
        plt.legend()
        plt.xlim(0.5*self.params['fmin'], 2*self.params['fmax'])
        plt.ylim([1e-44, 5e-40])
        plt.grid()
        plt.savefig(self.params['out_dir'] + '/diag_csd_' + str(ii+1) + str(jj+1) + '.png', dpi=200)
        print('Diagnostic spectra plot made in ' + self.params['out_dir'] + '/diag_csd_' + str(ii+1) + str(jj+1) + '.png')
        plt.close()
        
    def plot_spectra(self):
        '''
        A function to make a plot of the data spectrum. For use with external (non-autogenerated) data, where we cannot calculate the intrinsic components.
        '''
    
        # PSD from the FFTs
        data_PSD1, data_PSD2, data_PSD3  = np.mean(np.abs(self.r1)**2, axis=1), np.mean(np.abs(self.r2)**2, axis=1), np.mean(np.abs(self.r3)**2, axis=1)
    
        # "Cut" to desired frequencies
        idx = np.logical_and(self.fdata >=  self.params['fmin'] , self.fdata <=  self.params['fmax'])
        psdfreqs = self.fdata[idx]
    
        # Get desired frequencies for the PSD
        data_PSD1,data_PSD2, data_PSD3 = data_PSD1[idx], data_PSD2[idx], data_PSD3[idx]
        
        plt.loglog(psdfreqs, data_PSD1,label='PSD (1)', alpha=0.6, color='slategrey')
        plt.loglog(psdfreqs, data_PSD2,label='PSD (2)', alpha=0.6, color='rosybrown')
        plt.loglog(psdfreqs, data_PSD3,label='PSD (3)', alpha=0.6, color='mediumseagreen')
        plt.xlabel('$f$ in Hz')
        plt.ylabel('PSD 1/Hz ')
        plt.legend()
        plt.grid(linestyle=':',linewidth=0.5 )
        plt.xlim(0.5*self.params['fmin'], 2*self.params['fmax'])
    
        plt.savefig(self.params['out_dir'] + '/data_psd.png', dpi=200)
        print('Data spectra plot made in ' + self.params['out_dir'] + '/data_psd.png')
        plt.close()


def blip(paramsfile='params.ini',resume=False):
    '''
    The main workhorse of the bayesian pipeline.

    Input:
    Params File

    Output: Files containing evidence and pdfs of the parameters
    '''


    #  --------------- Read the params file --------------------------------

    # Initialize Dictionaries
    params = {}
    inj = {}

    config = configparser.ConfigParser()
    config.read(paramsfile)

    # Params Dict
    params['fmin']     = float(config.get("params", "fmin"))
    params['fmax']     = float(config.get("params", "fmax"))
    params['dur']      = float(config.get("params", "duration"))
    params['seglen']   = float(config.get("params", "seglen"))
    params['fs']       = float(config.get("params", "fs"))
    params['Shfile']   = config.get("params", "Shfile")
    params['mldc'] = int(config.get("params", "mldc"))
    params['datatype'] = str(config.get("params", "datatype"))
    params['datafile']  = str(config.get("params", "datafile"))
    params['fref'] = float(config.get("params", "fref"))
    
    params['model'] = str(config.get("params", "model"))

    params['tdi_lev'] = str(config.get("params", "tdi_lev"))
    params['lisa_config'] = str(config.get("params", "lisa_config"))
    params['nside'] = int(config.get("params", "nside"))
    params['lmax'] = int(config.get("params", "lmax"))
    params['tstart'] = float(config.get("params", "tstart"))

    ## see if we need to initialize the spherical harmonic subroutines
    sph_check = [sublist.split('_')[-1] for sublist in params['model'].split('+')]

    # Injection Dict
    inj['doInj']         = int(config.get("inj", "doInj"))
    
    if inj['doInj']:
        inj['injection'] = str(config.get("inj", "injection"))
        
        ## get the injection truevals, passed as a dict
        truevals = eval(str(config.get("inj","truevals")))
        ## some quantities we want to use as log values, so convert them
        log_list = ["Np","Na","omega0","fbreak","fcut","fscale"]
        for item in truevals.keys():
            if item in log_list:
                new_name = "log_"+item
                inj[new_name] = np.log10(truevals[item])
            else:
                inj[item] = truevals[item]
        ## add injections to the spherical harmonic check if needed
        sph_check = sph_check + [sublist.split('_')[-1] for sublist in inj['injection'].split('+')]
        
    ## set sph flags
    params['sph_flag'] = ('sph' in sph_check) or ('hierarchical' in sph_check)
    inj['sph_flag'] = np.any([(item not in ['noise','isgwb']) for item in sph_check])
    inj['pop_flag'] = 'population' in sph_check
    
    if inj['sph_flag']:
        try:
            inj['inj_lmax'] = int(config.get("inj", "inj_lmax"))
        except configparser.NoOptionError as err:
            if params['sph_flag']:
                print("Performing a spherical harmonic basis injection and inj_lmax has not been specified. Injection and recovery will use same lmax (lmax={}).".format(params['lmax']))
                inj['inj_lmax'] = params['lmax']
            else:
                print("You are trying to do a spherical harmonic injection, but have not specified lmax.")
                if 'lmax' in params.keys():
                    print("Warning: using analysis lmax parameter for inj_lmax, but you are not performing a spherical harmonic analysis.")
                    inj['inj_lmax'] = params['lmax']
                else:
                    raise err
    
    if inj['doInj'] and inj['pop_flag']:
        inj['popfile']     = str(config.get("inj","popfile"))
        try:
            inj['SNRcut']  = float(config.get("inj","SNRcut"))
        except configparser.NoOptionError:
            inj['SNRcut'] = 7
        colnames = str(config.get("inj","columns"))
        colnames = colnames.split(',')
        inj['columns'] = colnames
        delimiter = str(config.get("inj","delimiter"))
        if delimiter == 'space':
            delimiter = ' '
        elif delimiter == 'tab':
            delimiter = '\t'
        inj['delimiter'] = delimiter


    # some run parameters
    params['out_dir']            = str(config.get("run_params", "out_dir"))
    params['doPreProc']          = int(config.get("run_params", "doPreProc"))
    params['input_spectrum']     = str(config.get("run_params", "input_spectrum"))
    params['projection']         = str(config.get("run_params", "projection"))
    params['FixSeed']            = str(config.get("run_params", "FixSeed"))
    params['seed']               = int(config.get("run_params", "seed"))
    nlive                        = int(config.get("run_params", "nlive"))
    nthread                      = int(config.get("run_params", "Nthreads"))
    
    ## sampler selection
    params['sampler'] = str(config.get("run_params", "sampler"))
    
    ## sampler setup and late-time imports to reduce dependencies
    ## dynesty
    if params['sampler'] == 'dynesty':
        from src.dynesty_engine import dynesty_engine
    # nessai
    elif params['sampler'] == 'nessai':
        from src.nessai_engine import nessai_engine
        ## flow tuning
        params['nessai_neurons']     = str(config.get("run_params", "nessai_neurons"))
        if params['nessai_neurons']=='manual':
            params['n_neurons']      = int(config.get("run_params", "n_neurons"))
        params['reset_flow']         = int(config.get("run_params", "reset_flow"))
    ## emcee
    elif params['sampler'] == 'emcee':
        from src.emcee_engine import emcee_engine
        params['Nburn'] = int(config.get("run_params", "Nburn"))
        params['Nsamples'] = int(config.get("run_params", "Nsamples"))
    else:
        raise ValueError("Unknown sampler. Can be 'dynesty', 'emcee', or 'nessai' for now.")
    # checkpointing (dynesty+nessai only for now)
    if params['sampler']=='dynesty' or params['sampler'] == 'nessai':
        params['checkpoint']            = int(config.get("run_params", "checkpoint"))
        params['checkpoint_interval']   = float(config.get("run_params", "checkpoint_interval"))

    # Fix random seed
    if params['FixSeed']:
        from tools.SetRandomState import SetRandomState as setrs
        seed = params['seed']
        randst = setrs(seed)
    else:
        if params['checkpoint']:
            raise TypeError("Checkpointing without a fixed seed is not supported. Set 'FixSeed' to true and specify 'seed'.")
        if resume:
            raise TypeError("Resuming from a checkpoint requires re-generation of data, so the random seed MUST be fixed.")
        randst = None


    if not resume:
        # Make directories, copy stuff
        # Make output folder
        subprocess.call(["mkdir", "-p", params['out_dir']])
    
        # Copy the params file to outdir, to keep track of the parameters of each run.
        subprocess.call(["cp", paramsfile, params['out_dir']])
        
        # Initialize lisa class
        lisa =  LISA(params, inj)
        
        
    else:
        print("Resuming a previous analysis. Reloading data and sampler state...")

    if params['sampler'] == 'dynesty':
        # Create engine
        if not resume:
            # multiprocessing
            if nthread > 1:
                pool = Pool(nthread)
            else:
                pool = None
            engine, parameters = dynesty_engine().define_engine(lisa, params, nlive, nthread, randst, pool=pool)    
        else:
            pool = None
            if nthread > 1:
                print("Warning: Nthread > 1, but multiprocessing is not supported when resuming a run. Pool set to None.")
                ## To anyone reading this and wondering why:
                ## The pickle calls used by Python's multiprocessing fail when trying to run the sampler after saving/reloading it.
                ## This is because pickling the sampler maps all its attributes to their full paths;
                ## e.g., dynesty_engine.isgwb_prior is named as src.dynesty_engine.dynesty_engine.isgwb_prior
                ## BUT the object itself is still e.g. <function dynesty_engine.isgwb_prior at 0x7f8ebcc27130>
                ## so we get an error like
                ## _pickle.PicklingError: Can't pickle <function dynesty_engine.isgwb_prior at 0x7f8ebcc27130>: \
                ##                        it's not the same object as src.dynesty_engine.dynesty_engine.isgwb_prior
                ## See e.g. https://stackoverflow.com/questions/1412787/picklingerror-cant-pickle-class-decimal-decimal-its-not-the-same-object
                ## After too much time and sanity spent trying to fix this, I have admitted defeat.
                ## Feel free to try your hand -- maybe you're the chosen one. Good luck.
                
            engine, parameters = dynesty_engine.load_engine(params,randst,pool)
        ## run sampler
        if params['checkpoint']:
            checkpoint_file = params['out_dir']+'/checkpoint.pickle'
            t1 = time.time()
            post_samples, logz, logzerr = dynesty_engine.run_engine_with_checkpointing(engine,parameters,params['checkpoint_interval'],checkpoint_file)
            t2= time.time()
            print("Elapsed time to converge: {} s".format(t2-t1))
        else:
            t1 = time.time()
            post_samples, logz, logzerr = dynesty_engine.run_engine(engine)
            t2= time.time()
            print("Elapsed time to converge: {} s".format(t2-t1))
        if nthread > 1:
            engine.pool.close()
            engine.pool.join()
        # Save posteriors to file
        np.savetxt(params['out_dir'] + "/post_samples.txt",post_samples)
        np.savetxt(params['out_dir'] + "/logz.txt", logz)
        np.savetxt(params['out_dir'] + "/logzerr.txt", logzerr)

    elif params['sampler'] == 'emcee':

        # Create engine
        engine, parameters, init_samples = emcee_engine.define_engine(lisa.Model, nlive, randst)
        unit_samples, post_samples = emcee_engine.run_engine(engine, lisa.Model, init_samples,params['Nburn'],params['Nsamples'])

        # Save posteriors to file
        np.savetxt(params['out_dir'] + "/unit_samples.txt",unit_samples)
        np.savetxt(params['out_dir'] + "/post_samples.txt",post_samples)

    elif params['sampler'] == 'nessai':
        # Create engine
        if not resume:
            engine, parameters, model = nessai_engine().define_engine(lisa, params, nlive, nthread, params['seed'], params['out_dir']+'/nessai_output/',checkpoint_interval=params['checkpoint_interval'])    
        else:
            engine, parameters, model = nessai_engine.load_engine(params,nlive,nthread,params['seed'],params['out_dir']+'/nessai_output/',checkpoint_interval=params['checkpoint_interval'])
        ## run sampler
        if params['checkpoint']:
            checkpoint_file = params['out_dir']+'/checkpoint.pickle'
            t1 = time.time()
            post_samples, logz, logzerr = nessai_engine.run_engine_with_checkpointing(engine,parameters,model,params['out_dir']+'/nessai_output/',checkpoint_file)
            t2= time.time()
            print("Elapsed time to converge: {} s".format(t2-t1))
            np.savetxt(params['out_dir']+'/time_elapsed.txt',np.array([t2-t1]))
        else:
            t1 = time.time()
            post_samples, logz, logzerr = nessai_engine.run_engine(engine,parameters,model,params['out_dir']+'/nessai_output/')
            t2= time.time()
            print("Elapsed time to converge: {} s".format(t2-t1))
            np.savetxt(params['out_dir']+'/time_elapsed.txt',np.array([t2-t1]))

        # Save posteriors to file
        np.savetxt(params['out_dir'] + "/post_samples.txt",post_samples)
#        np.savetxt(params['out_dir'] + "/logz.txt", logz)
#        np.savetxt(params['out_dir'] + "/logzerr.txt", logzerr)
    
    else:
        raise TypeError('Unknown sampler model chosen. Only dynesty, nessai, & emcee are supported')


    # Save parameters as a pickle
    with open(params['out_dir'] + '/config.pickle', 'wb') as outfile:
        pickle.dump(params, outfile)
        pickle.dump(inj, outfile)
        pickle.dump(parameters, outfile)

    print("\nMaking posterior Plots ...")
    plotmaker(post_samples, params, parameters, inj, lisa.Model, lisa.Injection)
    if not params['mldc']:
        fitmaker(post_samples, params, parameters, inj, lisa.Model, lisa.Injection)
    else:
        fitmaker(post_samples, params, parameters, inj, lisa.Model)
    ## make a map if there is a map to be made
    if np.any([lisa.Model.submodels[sm_name].has_map for sm_name in lisa.Model.submodel_names]):
        if 'healpy_proj' in params.keys():
            mapmaker(post_samples, params, parameters, inj, lisa.Model, lisa.Injection, coord=params['healpy_proj'])
        else:
            mapmaker(post_samples, params, parameters, inj, lisa.Model, lisa.Injection)
        
    

if __name__ == "__main__":

    if len(sys.argv) != 2:
        if sys.argv[2] == 'resume':
            blip(sys.argv[1],resume=True)
        else:
            raise ValueError('Provide (only) the params file as an argument')
    else:
        blip(sys.argv[1])
