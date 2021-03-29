## def acolite_l2w
## new L2W parameter computation for L2R generic extracted miniscene
## written by Quinten Vanhellemont, RBINS
## 2021-03-09
## modifications:


def acolite_l2w(gem,
                settings = None,
                sub = None,
                target_file = None,
                output = None,
                load_data = True,
                return_gem = False,
                copy_datasets = ['lon', 'lat'],
                new = True,
                verbosity=5):

    import os
    import numpy as np
    import acolite as ac
    import scipy.ndimage
    import skimage.color

    ## read gem file if NetCDF
    if type(gem) is str:
        gemf = '{}'.format(gem)
        gem = ac.gem.read(gem, sub=sub, load_data=load_data)
    gemf = gem['gatts']['gemfile']

    ## set up output file
    if target_file is None:
        output_name = os.path.basename(gemf).replace('.nc', '')
        output_name = output_name.replace('_L2R', '_L2W')
        odir = output if output is not None else os.path.dirname(gemf)
        ofile = '{}/{}.nc'.format(odir, output_name)
    else:
        ofile = '{}'.format(target_file)

    ## combine default and user defined settings
    setu = ac.acolite.settings.parse(gem['gatts']['sensor'], settings=settings)

    ## get rhot and rhos wavelengths
    rhot_ds = [ds for ds in gem['datasets'] if 'rhot_' in ds]
    rhot_waves = [int(ds.split('_')[1]) for ds in rhot_ds]
    if len(rhot_waves) == 0: print('{} is probably not an ACOLITE L2R file: {} rhot datasets.'.format(gemf, len(rhot_ds)))

    rhos_ds = [ds for ds in gem['datasets'] if 'rhos_' in ds]
    rhos_waves = [int(ds.split('_')[1]) for ds in rhos_ds]
    if len(rhos_waves) == 0: print('{} is probably not an ACOLITE L2R file: {} rhos datasets.'.format(gemf, len(rhos_ds)))

    ## read rsr
    rsrd = ac.shared.rsr_dict(sensor=gem['gatts']['sensor'])

    ## compute flag value to mask for water products
    flag_value = 0
    if setu['l2w_mask']:
        flag_value = 2**setu['flag_exponent_swir']
        if setu['l2w_mask_cirrus']: flag_value += 2**setu['flag_exponent_cirrus']
        if setu['l2w_mask_high_toa']: flag_value += 2**setu['flag_exponent_toa']
        if setu['l2w_mask_negative_rhow']: flag_value += 2**setu['flag_exponent_negative']

    ## compute mask
    ## non water/swir threshold
    cidx,cwave = ac.shared.closest_idx(rhot_waves, setu['l2w_mask_wave'])
    cur_par = 'rhot_{}'.format(cwave)
    if cur_par in gem['data']:
        cur_data = 1.0 * gem['data'][cur_par]
    else:
        cur_data = ac.shared.nc_data(gemf, cur_par, sub=sub).data
    if setu['l2w_mask_smooth']:
        cur_data = ac.shared.fillnan(cur_data)
        cur_data = scipy.ndimage.gaussian_filter(cur_data, setu['l2w_mask_smooth_sigma'], mode='reflect')
    cur_mask = cur_data > setu['l2w_mask_threshold']
    cur_data = None
    l2_flags = cur_mask.astype(np.int32)*(2**setu['flag_exponent_swir'])
    cur_mask = None
    ## cirrus masking
    cidx,cwave = ac.shared.closest_idx(rhot_waves, setu['l2w_mask_cirrus_wave'])
    if np.abs(cwave - setu['l2w_mask_cirrus_wave']) < 5:
        cur_par = 'rhot_{}'.format(cwave)
        if cur_par in gem['data']:
            cur_data = 1.0 * gem['data'][cur_par]
        else:
            cur_data = ac.shared.nc_data(gemf, cur_par, sub=sub).data
        if setu['l2w_mask_smooth']:
            cur_data = ac.shared.fillnan(cur_data)
            cur_data = scipy.ndimage.gaussian_filter(cur_data, setu['l2w_mask_smooth_sigma'], mode='reflect')
        cirrus_mask = cur_data > setu['l2w_mask_cirrus_threshold']
        cirrus = None
        l2_flags += cirrus_mask.astype(np.int32)*(2**setu['flag_exponent_cirrus'])
        cirrus_mask = None
    else:
        if verbosity > 2: print('No suitable band found for cirrus masking.')
    ## TOA out of limit
    toa_mask = None
    for ci, cur_par in enumerate(rhot_ds):
        if cur_par in gem['data']:
            cur_data = 1.0 * gem['data'][cur_par]
        else:
            cur_data = ac.shared.nc_data(gemf, cur_par, sub=sub).data
        if setu['l2w_mask_smooth']:
            cur_data = ac.shared.fillnan(cur_data)
            cur_data = scipy.ndimage.gaussian_filter(cur_data, setu['l2w_mask_smooth_sigma'], mode='reflect')
        if toa_mask is None: toa_mask = np.zeros(cur_data.shape).astype(bool)
        toa_mask = (toa_mask) | (cur_data > setu['l2w_mask_high_toa_threshold'])
    l2_flags = (l2_flags) | (toa_mask.astype(np.int32)*(2**setu['flag_exponent_toa']))
    toa_mask = None
    ## negative rhos
    neg_mask = None
    for ci, cur_par in enumerate(rhos_ds):
        if rhos_waves[ci]<setu['l2w_mask_negative_wave_range'][0]: continue
        if rhos_waves[ci]>setu['l2w_mask_negative_wave_range'][1]: continue
        if cur_par in gem['data']:
            cur_data = 1.0 * gem['data'][cur_par]
        else:
            cur_data = ac.shared.nc_data(gemf, cur_par, sub=sub).data
        #if setu['l2w_mask_smooth']: cur_data = scipy.ndimage.gaussian_filter(cur_data, setu['l2w_mask_smooth_sigma'])
        if neg_mask is None: neg_mask = np.zeros(cur_data.shape).astype(bool)
        neg_mask = (neg_mask) | (cur_data < 0)
    l2_flags = (l2_flags) | (neg_mask.astype(np.int32)*(2**setu['flag_exponent_negative']))
    neg_mask = None

    ## list datasets to copy over from L2R
    for cur_par in gem['data']:
        if (cur_par in setu['l2w_parameters']):
            copy_datasets.append(cur_par)
        if (('rhot_*' in setu['l2w_parameters']) & ('rhot_' in cur_par)):
            copy_datasets.append(cur_par)
        if (('rhos_*' in setu['l2w_parameters']) & ('rhos_' in cur_par)):
            copy_datasets.append(cur_par)
        if (('rhow_*' in setu['l2w_parameters']) & ('rhos_' in cur_par)):
            copy_datasets.append(cur_par.replace('rhos_', 'rhow_'))
        if (('Rrs_*' in setu['l2w_parameters']) & ('rhos_' in cur_par)):
            copy_datasets.append(cur_par.replace('rhos_', 'Rrs_'))

    ## copy datasets
    for ci, cur_par in enumerate(copy_datasets):
        factor = 1.0
        cur_tag = '{}'.format(cur_par)
        mask = False
        ## copy Rrs/rhow
        if 'Rrs_' in cur_par:
            factor = 1.0/np.pi
            cur_tag = cur_par.replace('Rrs_','rhos_')
            mask = True
        if 'rhow_' in cur_par:
            factor = 1.0
            cur_tag = cur_par.replace('rhow_','rhos_')
            mask = True
        ## if data already read copy here
        if cur_tag in gem['data']:
            cur_data = factor * gem['data'][cur_tag]
            cur_att = gem['atts'][cur_tag]
        else:
            cur_d, cur_att = ac.shared.nc_data(gemf, cur_tag, sub=sub, attributes=True)
            cur_data = factor * cur_d.data
            cur_data[cur_d.mask] = np.nan
            cur_d = None
        ## apply mask to Rrs and rhow
        if mask: cur_data[(l2_flags & flag_value)!=0] = np.nan
        if verbosity > 1: print('Writing {}'.format(cur_par))
        ac.output.nc_write(ofile, cur_par, cur_data, dataset_attributes=cur_att, attributes=gem['gatts'], new=new)
        cur_data = None
        new = False

    ## write l2 flags
    ac.output.nc_write(ofile, 'l2_flags', l2_flags, attributes=gem['gatts'], new=new)
    if return_gem: gem['data']['l2_flags'] = l2_flags
    new = False

    ## parameter loop
    ## compute other parameters
    for cur_par in setu['l2w_parameters']:
        if cur_par.lower() in ['rhot_*', 'rhos_*', 'rrs_*', 'rhow_*']: continue ## we have copied these above
        if cur_par.lower() in [ds.lower() for ds in ac.shared.nc_datasets(ofile)]: continue ## parameter already in output dataset (would not work if we are appending subsets to the ncdf)

        ## split on underscores
        sp = cur_par.split('_')

        ## default mask and empty dicts for current parameter
        mask = False
        par_data = {}
        par_atts = {}

        #############################
        ## Nechad turbidity/spm
        if 'nechad' in cur_par:
            mask = True ## water parameter so apply mask

            nechad_parameter = 'centre'
            if '2016' in cur_par: nechad_parameter = '2016'
            if 'ave' in cur_par: nechad_parameter = 'resampled'

            ## turbidity
            if cur_par[0] == 't':
                nechad_par = 'TUR'
                par_attributes = {'algorithm':'Nechad et al. 2009', 'title':'Nechad Turbidity'}
                par_attributes['standard_name']='turbidity'
                par_attributes['long_name']='Water turbidity'
                par_attributes['units']='FNU'
                par_attributes['reference']='Nechad et al. 2009'
                par_attributes['algorithm']='2009 calibration'
            elif cur_par[0] == 's':
                nechad_par = 'SPM'
                par_attributes = {'algorithm':'Nechad et al. 2010', 'title':'Nechad SPM'}
                par_attributes['standard_name']='spm'
                par_attributes['long_name']='Suspended Particulate Matter'
                par_attributes['units']='g m^-3'
                par_attributes['reference']='Nechad et al. 2010'
                par_attributes['algorithm']='2010 calibration'
            else:
                continue

            ## find out which band to use
            nechad_band = None
            nechad_wave = 665
            sp = cur_par.split('_')
            if 'ave' not in cur_par:
                if len(sp) > 2: nechad_wave = sp[2]
            else:
                if len(sp) > 3: nechad_wave = sp[3]

            ci, cw = ac.shared.closest_idx(rhos_waves, int(nechad_wave))
            for b in rsrd[gem['gatts']['sensor']]['rsr_bands']:
                if (rsrd[gem['gatts']['sensor']]['wave_name'][b] == str(cw)): nechad_band = b
            print(nechad_wave, nechad_band)

            A_Nechad, C_Nechad = None, None

            ## band center
            if nechad_parameter == 'centre':
                par_name = '{}_Nechad_{}'.format(nechad_par, cw)
                nechad_dict = ac.parameters.nechad.coef_hyper(nechad_par)
                didx,algwave = ac.shared.closest_idx(nechad_dict['wave'], nechad_wave)
                A_Nechad = nechad_dict['A'][didx]
                C_Nechad = nechad_dict['C'][didx]

            ## resampled to band
            if nechad_parameter == 'resampled':
                par_name = '{}_Nechad_{}_ave'.format(nechad_par, cw)
                nechad_dict = ac.parameters.nechad.coef_hyper(nechad_par)
                ## resample parameters to band
                cdct = ac.shared.rsr_convolute_dict(nechad_dict['wave']/1000, nechad_dict['C'], rsrd[gem['gatts']['sensor']]['rsr'])
                adct = ac.shared.rsr_convolute_dict(nechad_dict['wave']/1000, nechad_dict['A'], rsrd[gem['gatts']['sensor']]['rsr'])
                A_Nechad = adct[nechad_band]
                C_Nechad = cdct[nechad_band]

            ## resampled to band by Nechad 2016
            if nechad_parameter == '2016':
                par_name = '{}_Nechad2016_{}'.format(nechad_par, cw)
                par_attributes['algorithm']='2016 calibration'
                nechad_dict = ac.shared.coef_nechad_2016()
                for k in nechad_dict:
                    if k['sensor'] != gem['gatts']['sensor']: continue
                    if k['band'] != 'B{}'.format(nechad_band): continue
                    if k['par'] != nechad_par: continue
                    A_Nechad = k['A']
                    C_Nechad = k['C']

            ## if we have A and C we can continue
            if (A_Nechad is not None) & (C_Nechad is not None):
                cur_ds = 'rhos_{}'.format(cw)
                if cur_ds in gem['data']:
                    cur_data = 1.0 * gem['data'][cur_ds]
                else:
                    cur_data = ac.shared.nc_data(gemf, cur_ds, sub=sub).data
                ## compute parameter
                cur_data = (A_Nechad * cur_data) / (1.-(cur_data/C_Nechad))
                par_data[par_name] = cur_data
                par_atts[par_name] = par_attributes
                par_atts[par_name]['ds_name'] = par_name
                par_atts[par_name]['A_{}'.format(nechad_par)] = A_Nechad
                par_atts[par_name]['C_{}'.format(nechad_par)] = C_Nechad
        ## end nechad turbidity/spm
        #############################

        #############################
        ## start Dogliotti turbidity
        if 'dogliotti' in cur_par:
            mask = True ## water parameter so apply mask

            par_attributes = {'algorithm':'Dogliotti et al. 2015', 'title':'Dogliotti Turbidity'}
            par_attributes['standard_name']='turbidity'
            par_attributes['long_name']='Water turbidity'
            par_attributes['units']='FNU'
            par_attributes['reference']='Dogliotti et al. 2015'
            par_attributes['algorithm']=''

            ## get config
            par_name = 'TUR_Dogliotti'
            dcfg = 'defaults'
            dogliotti_par = 'blended'
            if len(sp) > 2:
                if sp[2] not in ['red', 'nir']:
                    dcfg = sp[2]
                else:
                    dogliotti_par = sp[2]
                par_name+='_{}'.format(dogliotti_par)
            par_attributes['ds_name'] = par_name
            cfg = ac.parameters.dogliotti.coef(config=dcfg)

            ## identify bands
            ri, rw = ac.shared.closest_idx(rhos_waves, int(cfg['algo_wave_red']))
            ni, nw = ac.shared.closest_idx(rhos_waves, int(cfg['algo_wave_nir']))
            for b in rsrd[gem['gatts']['sensor']]['rsr_bands']:
                if (rsrd[gem['gatts']['sensor']]['wave_name'][b] == str(rw)): red_band = b
                if (rsrd[gem['gatts']['sensor']]['wave_name'][b] == str(nw)): nir_band = b

            ## store settings in atts
            for k in cfg: par_attributes[k] = cfg[k]
            par_attributes['wave_red'] = rw
            par_attributes['wave_nir'] = nw

            ## read red data
            cur_ds = 'rhos_{}'.format(rw)
            if cur_ds in gem['data']:
                red = 1.0 * gem['data'][cur_ds]
            else:
                red = ac.shared.nc_data(gemf, cur_ds, sub=sub).data
            tur = (par_attributes['A_T_red'] * red) / (1.-red/par_attributes['C_T_red'])

            ## read nir data
            cur_ds = 'rhos_{}'.format(nw)
            if cur_ds in gem['data']:
                nir = 1.0 * gem['data'][cur_ds]
            else:
                nir = ac.shared.nc_data(gemf, cur_ds, sub=sub).data
            nir_tur = (par_attributes['A_T_nir'] * nir) / (1.-nir/par_attributes['C_T_nir'])

            if dogliotti_par == 'blended':
                ## replace most turbid with nir band
                dsub = np.where(red >= par_attributes['upper_lim'])
                if len(dsub[0]) > 0: tur[dsub] = nir_tur[dsub]
                ## blend in between
                dsub = np.where((red < par_attributes['upper_lim']) & (red >= par_attributes['lower_lim']))
                if len(dsub[0]) > 0:
                    w=(red[dsub]  - par_attributes['lower_lim']) / (par_attributes['upper_lim']-par_attributes['lower_lim'])
                    tur[dsub] = ((1.-w) * tur[dsub]) + (w*nir_tur[dsub])
                par_data[par_name] = tur
                par_atts[par_name] = par_attributes
            elif dogliotti_par == 'red':
                par_data[par_name] = tur
                par_atts[par_name] = par_attributes
            elif dogliotti_par == 'nir':
                par_data[par_name] = nir_tur
                par_atts[par_name] = par_attributes
            red = None
            nir = None
        ## end Dogliotti turbidity
        #############################

        #############################
        ## CHL_OC
        if 'chl_oc' in cur_par:
            mask = True ## water parameter so apply mask
            ## load config
            chl_oc_wl_diff = 20
            cfg = ac.parameters.chl_oc.coef()
            if gem['gatts']['sensor'] not in cfg:
                print('{} not configured for {}'.format(cur_par, gem['gatts']['sensor']))
                continue

            par_attributes = {'algorithm':'Chlorophyll a blue/green ratio', 'dataset':'rhos'}
            par_attributes['standard_name']='chlorophyll_concentration'
            par_attributes['long_name']='Chlorophyll a concentration derived from blue green ratio'
            par_attributes['units']='mg m^-3'
            par_attributes['reference']='Franz et al. 2015'
            par_attributes['algorithm']=''

            if (cur_par == 'chl_oc') | (cur_par == 'chl_oc2'):
                par_name = 'chl_oc2'
            elif (cur_par == 'chl_oc3'):
                par_name = 'chl_oc3'
            else:
                par_name = cur_par

            if par_name not in cfg[gem['gatts']['sensor']]:
                print('{} not configured for {}'.format(par_name, gem['gatts']['sensor']))
                continue
            par_attributes['ds_name']=par_name
            chl_dct = cfg[gem['gatts']['sensor']][par_name]

            ## get bands
            blue, green = None, None
            for w in chl_dct['blue'] + chl_dct['green']:
                ci, cw = ac.shared.closest_idx(rhos_waves, int(w))
                if np.abs(cw-w) > chl_oc_wl_diff: continue
                cur_ds = 'rhos_{}'.format(cw)
                if cur_ds in gem['data']:
                    cur_data = 1.0 * gem['data'][cur_ds]
                else:
                    cur_data = ac.shared.nc_data(gemf, cur_ds, sub=sub).data
                if w in chl_dct['blue']:
                    if blue is None:
                        par_attributes['blue_wave_sel'] = [cw]
                        blue = 1.0 * cur_data
                    else:
                        par_attributes['blue_wave_sel'] += [cw]
                        blue = np.nanmax((blue, cur_data), axis=0)
                if w in chl_dct['green']:
                    if green is None:
                        par_attributes['green_wave_sel'] = [cw]
                        green = 1.0 * cur_data
            if (blue is None) | (green is None): continue

            ## compute CHL
            ratio = np.log10(blue/green)
            blue, green = None, None
            par_data[par_name] = chl_coef[0] + chl_coef[1] * ratio + \
                                                     chl_coef[2] * ratio * ratio + \
                                                     chl_coef[3] * ratio * ratio * ratio + \
                                                     chl_coef[4] * ratio * ratio * ratio * ratio
            par_data[par_name] = np.power(10, par_data[par_name])
            par_atts[par_name] = par_attributes
        ## end CHL_OC
        #############################

        #############################
        ## QAA
        if (cur_par == 'qaa') | (cur_par == 'qaa5') | (cur_par == 'qaa6') | (cur_par == 'qaaw') |\
           ('_qaa5' in cur_par) | ('_qaa6' in cur_par) | ('_qaaw' in cur_par):
            print('QAA')
            mask = True ## water parameter so apply mask
            sensor = gem['gatts']['sensor']
            if sensor not in ['L8_OLI', 'S2A_MSI', 'S2B_MSI']:
                print('QAA not configured for {}'.format(gem['gatts']['sensor']))
                continue

            par_attributes = {'algorithm':'QAA', 'dataset':'rhos'}
            par_attributes['standard_name']='qaa'
            par_attributes['long_name']='Quasi Analytical Algorithm outputs'
            par_attributes['units']='various'
            par_attributes['reference']='Lee et al. 2002'
            par_attributes['algorithm']=''

            qaa_coef = ac.parameters.qaa.qaa_coef()
            qaa_wave = [443, 490, 560, 665]
            sen_wave = []

            for ki, k in enumerate(qaa_wave):
                ci, cw = ac.shared.closest_idx(rhos_waves, k)
                cur_ds = 'rhos_{}'.format(cw)
                sen_wave.append(cw)
                if ki == 0: qaa_in = {}
                if cur_ds in gem['data']:
                    cur_data  = 1.0 * gem['data'][cur_ds]
                else:
                    cur_data  = ac.shared.nc_data(gemf, cur_ds, sub=sub).data
                ## mask data
                if mask: cur_data[(l2_flags & flag_value)!=0] = np.nan
                ## convert to Rrs
                qaa_in[k] = cur_data/np.pi

            ## get sun zenith angle
            if 'sza' in gem['data']:
                sza = gem['data']['sza']
            else:
                sza = gem['gatts']['sza']

            ## run qaa
            ret = ac.parameters.qaa.qaa_compute(qaa_in, qaa_coef = qaa_coef,
                                        sza=sza, satellite=sensor[0:2])
            ## list possible output parameters
            qaa_pars = list(ret.keys())
            cur_par_out = []
            ## check which parameters are wanted
            if ('qaa5' in setu['l2w_parameters']) or ('qaa' in setu['l2w_parameters']):
                cur_par_out += ['qaa_{}'.format(k) for k in qaa_pars if ('_v' not in k) and ('qaa_{}'.format(k) not in cur_par_out)]
                cur_par_out += ['qaa_{}'.format(k) for k in qaa_pars if (k[-2:] == 'v5')]
                print(cur_par_out)
            if ('qaa6' in setu['l2w_parameters']) or ('qaa' in setu['l2w_parameters']):
                cur_par_out += ['qaa_{}'.format(k) for k in qaa_pars if ('_v' not in k) and ('qaa_{}'.format(k) not in cur_par_out)]
                cur_par_out += ['qaa_{}'.format(k) for k in qaa_pars if (k[-2:] == 'v6')]
            if ('qaaw' in setu['l2w_parameters']) or ('qaa' in setu['l2w_parameters']):
                cur_par_out += ['qaa_{}'.format(k) for k in qaa_pars if ('_v' not in k) and ('qaa_{}'.format(k) not in cur_par_out)]
                cur_par_out += ['qaa_{}'.format(k) for k in qaa_pars if (k[-2:] == 'vw')]
            cur_par_out += [k for k in setu['l2w_parameters'] if (k[4:] in qaa_pars) and (k not in cur_par_out)]
            cur_par_out.sort()

            ## reformat for output
            for p in cur_par_out:
                par_data[p] = ret[p[4:]] * 1.0
                ret[p[4:]] = None
                par_atts[p] = par_attributes
                par_atts[p]['ds_name'] = p
            ret = None
        ## end QAA
        #############################

        #############################
        ## Pitarch 3 band QAA
        if cur_par[0:5] == 'p3qaa':
            mask = True ## water parameter so apply mask
            ## load config
            cfg = ac.parameters.pitarch.p3qaa_coef()
            if gem['gatts']['sensor'] not in cfg:
                print('P3QAA not configured for {}'.format(gem['gatts']['sensor']))
                continue

            par_attributes = {'algorithm':'Pitarch et al. in prep.'}

            ## read Blue Green Red data, convert to Rrs
            for k in ['B', 'G', 'R']:
                ci, cw = ac.shared.closest_idx(rhos_waves, cfg[gem['gatts']['sensor']]['center_wl'][k])
                cur_ds = 'rhos_{}'.format(cw)
                if cur_ds in gem['data']:
                    cur_data = 1.0 * gem['data'][cur_ds]
                else:
                    cur_data = ac.shared.nc_data(gemf, cur_ds, sub=sub).data
                if mask: cur_data[(l2_flags & flag_value)!=0] = np.nan
                if k == 'B':
                    B = cur_data / np.pi
                    Bwave = cw
                if k == 'G':
                    G = cur_data / np.pi
                    Gwave = cw
                if k == 'R':
                    R = cur_data / np.pi
                    Rwave = cw
                cur_data = None

            ## compute 3 band QAA
            print('Computing Pitarch 3 band QAA')
            print('R{} G{} B{}'.format(Rwave, Gwave, Bwave))
            ret = ac.parameters.pitarch.p3qaa_compute(gem['gatts']['sensor'], B, G, R)

            ## list possible output parameters
            p3_pars = []
            for k in ret:
                if len(ret[k].shape) == 3:
                    p3_pars += ['p3qaa_{}_{}'.format(k, Bwave), 'p3qaa_{}_{}'.format(k, Gwave), 'p3qaa_{}_{}'.format(k, Rwave)]
                else:
                    p3_pars += ['p3qaa_{}'.format(k)]
            ## check which parameters are wanted
            if 'p3qaa' in setu['l2w_parameters']:
                cur_par_out = p3_pars
            else:
                cur_par_out = [k for k in setu['l2w_parameters'] if k in p3_pars]

            ## reformat for output
            for p in cur_par_out:
                if p[6:] not in ret: ## this means we have a three band parameter
                    k = p[6:-4]
                    w = int(p[-3:])
                    if w == Bwave: wi = 0
                    if w == Gwave: wi = 1
                    if w == Rwave: wi = 2
                    par_data[p] = ret[k][:,:,wi]
                    par_atts[p] = par_attributes
                    par_atts[p]['ds_name'] = p
                else:
                    par_data[p] = ret[p[6:]]
                    par_atts[p] = par_attributes
                    par_atts[p]['ds_name'] = p
            ret = None
        ## end Pitarch 3 band QAA
        #############################

        #############################
        ## FAI
        if (cur_par == 'fai') | (cur_par == 'fai_rhot'):
            par_name = cur_par
            mask = False ## no water mask
            par_split = cur_par.split('_')
            par_attributes = {'algorithm':'Floating Algal Index, Hu et al. 2009', 'dataset':'rhos'}
            par_attributes['standard_name']='fai'
            par_attributes['long_name']='Floating Algal Index'
            par_attributes['units']="1"
            par_attributes['reference']='Hu et al. 2009'
            par_attributes['algorithm']=''

            ## select bands
            required_datasets,req_waves_selected = [],[]
            ds_waves = [w for w in rhos_waves]
            if cur_par=='fai_rhot':
                par_attributes['dataset']='rhot'
                ds_waves = [w for w in rhot_waves]
            ## wavelengths and max wavelength difference
            fai_diff = [10, 30, 80]
            req_waves = [660,865,1610]
            for i, reqw in enumerate(req_waves):
                widx,selwave = ac.shared.closest_idx(ds_waves, reqw)
                if abs(float(selwave)-float(reqw)) > fai_diff[i]: continue
                selds='{}_{}'.format(par_attributes['dataset'],selwave)
                required_datasets.append(selds)
                req_waves_selected.append(selwave)
            par_attributes['waves']=req_waves_selected
            if len(required_datasets) != len(req_waves): continue

            ## get data
            for di, cur_ds in enumerate(required_datasets):
                if di == 0: tmp_data = []
                if cur_ds in gem['data']:
                    cur_data  = 1.0 * gem['data'][cur_ds]
                else:
                    cur_data  = ac.shared.nc_data(gemf, cur_ds, sub=sub).data
                tmp_data.append(cur_data)
            ## compute fai
            fai_sc = (float(par_attributes['waves'][1])-float(par_attributes['waves'][0]))/\
                     (float(par_attributes['waves'][2])-float(par_attributes['waves'][0]))
            nir_prime = tmp_data[0] + (tmp_data[2]-tmp_data[0]) * fai_sc
            par_data[par_name] = tmp_data[1] - nir_prime
            par_atts[par_name] = par_attributes
            tmp_data = None
        ## end FAI
        #############################

        #############################
        ## FAIT
        if (cur_par == 'fait'):
            par_name = cur_par
            mask = False ## no water mask
            par_split = par_name.split('_')
            par_attributes = {'algorithm':'Floating Algal Index Turbid Waters, Dogliotti et al. 2018', 'dataset':'rhos'}
            par_attributes['standard_name']='fait'
            par_attributes['long_name']='Floating Algal Index for Turbid Waters'
            par_attributes['units']="1"
            par_attributes['reference']='Dogliotti et al. 2018'
            par_attributes['algorithm']=''

            ## read config
            fait_cfg = ac.shared.import_config('{}/Shared/algorithms/Dogliotti/dogliotti_fait.cfg'.format(ac.config['data_dir']))
            fait_fai_threshold = float(fait_cfg['fait_fai_threshold'])
            fait_red_threshold = float(fait_cfg['fait_red_threshold'])
            fait_rgb_limit = float(fait_cfg['fait_rgb_limit'])
            fait_L_limit = float(fait_cfg['fait_L_limit'])

            if gem['gatts']['sensor'] == 'L8_OLI':
                fait_a_threshold = float(fait_cfg['fait_a_threshold_OLI'])
            elif gem['gatts']['sensor'] in ['S2A_MSI', 'S2B_MSI']:
                fait_a_threshold = float(fait_cfg['fait_a_threshold_MSI'])
            else:
                print('Parameter {} not configured for {}.'.format(par_name,gem['gatts']['sensor']))
                continue

            ## add to parameter attributes
            par_attributes['fai_threshold'] = fait_fai_threshold
            par_attributes['red_threshold'] = fait_red_threshold
            par_attributes['rgb_limit'] = fait_rgb_limit
            par_attributes['L_limit'] = fait_L_limit
            par_attributes['a_threshold'] = fait_a_threshold

            ## select bands
            required_datasets,req_waves_selected = [],[]
            ds_waves = [w for w in rhos_waves]

            ## wavelengths and max wavelength difference
            fai_diff = [10, 10, 10, 30, 80]
            req_waves = [490, 560, 660, 865, 1610]
            for i, reqw in enumerate(req_waves):
                widx,selwave = ac.shared.closest_idx(ds_waves, reqw)
                if abs(float(selwave)-float(reqw)) > fai_diff[i]: continue
                selds='{}_{}'.format(par_attributes['dataset'],selwave)
                required_datasets.append(selds)
                req_waves_selected.append(selwave)
            par_attributes['waves']=req_waves_selected
            if len(required_datasets) != len(req_waves): continue

            ## get data
            for di, cur_ds in enumerate(required_datasets):
                if di == 0: tmp_data = []
                if cur_ds in gem['data']:
                    cur_data  = 1.0 * gem['data'][cur_ds]
                else:
                    cur_data  = ac.shared.nc_data(gemf, cur_ds, sub=sub).data
                tmp_data.append(cur_data)

            ## compute fait
            fai_sc = (float(par_attributes['waves'][3])-float(par_attributes['waves'][2]))/\
                     (float(par_attributes['waves'][4])-float(par_attributes['waves'][2]))
            nir_prime = tmp_data[2] + \
                        (tmp_data[4]-tmp_data[2]) * fai_sc
            par_data[par_name] = tmp_data[3] - nir_prime
            par_atts[par_name] = par_attributes
            nir_prime = None

            ## make lab coordinates
            for i in range(3):
                data = ac.shared.datascl(tmp_data[i], dmin=0, dmax=fait_rgb_limit)
                if i == 0:
                    rgb = data
                else:
                    rgb = np.dstack((rgb,data))
                data = None
            lab = skimage.color.rgb2lab(rgb)
            rgb = None

            ## check FAI > 0
            par_data[par_name][par_data[par_name] >= fait_fai_threshold] = 1.0
            par_data[par_name][par_data[par_name] < fait_fai_threshold] = 0.0

            ## check turbidity based on red threshold
            par_data[par_name][tmp_data[2] > fait_red_threshold] = 0.0

            ## check L and a
            par_data[par_name][lab[:,:,0] >= fait_L_limit] = 0.0
            par_data[par_name][lab[:,:,1] >= fait_a_threshold] = 0.0
            lab = None
        ## end FAIT
        #############################

        #############################
        ## NDVI
        if (cur_par == 'ndvi') | (cur_par == 'ndvi_rhot'):
            par_name = cur_par
            mask = False ## no water mask
            par_split = cur_par.split('_')
            par_attributes = {'algorithm':'NDVI', 'dataset':'rhos'}
            par_attributes['standard_name']='ndvi'
            par_attributes['long_name']='Normalised Difference Vegetation Index'
            par_attributes['units']="1"
            par_attributes['reference']=''
            par_attributes['algorithm']=''

            ## select bands
            required_datasets,req_waves_selected = [],[]
            ds_waves = [w for w in rhos_waves]
            if cur_par=='ndvi_rhot':
                par_attributes['dataset']='rhot'
                ds_waves = [w for w in rhot_waves]

            ## wavelengths and max wavelength difference
            ndvi_diff = [25, 45]
            req_waves = [660,865]
            for i, reqw in enumerate(req_waves):
                widx,selwave = ac.shared.closest_idx(ds_waves, reqw)
                if abs(float(selwave)-float(reqw)) > fai_diff[i]: continue
                selds='{}_{}'.format(par_attributes['dataset'],selwave)
                required_datasets.append(selds)
                req_waves_selected.append(selwave)
            par_attributes['waves']=req_waves_selected
            if len(required_datasets) != len(req_waves): continue
            ## get data
            for di, cur_ds in enumerate(required_datasets):
                if di == 0: tmp_data = []
                if cur_ds in gem['data']:
                    cur_data  = 1.0 * gem['data'][cur_ds]
                else:
                    cur_data  = ac.shared.nc_data(gemf, cur_ds, sub=sub).data
                tmp_data.append(cur_data)

            ## compute ndvi
            par_data[par_name] = (tmp_data[1]-tmp_data[0])/\
                                   (tmp_data[1]+tmp_data[0])
            par_atts[par_name] = par_attributes
            tmp_data = None
        ## end NDVI

        #############################
        ## NDCI
        if (cur_par == 'ndci'):
            par_name = cur_par
            mask = True ## apply non water mask
            par_attributes = {'algorithm':'Mishra et al. 2014, NDCI', 'dataset':'rhos'}
            par_attributes['standard_name']='ndci'
            par_attributes['long_name']='Normalised Difference Chlorophyll Index'
            par_attributes['units']="1"
            par_attributes['reference']='Mishra et al. 2014'
            par_attributes['algorithm']=''

            required_datasets,req_waves_selected = [],[]
            ds_waves = [w for w in rhos_waves]

            ### get required datasets
            if gem['gatts']['sensor'] not in ['S2A_MSI', 'S2B_MSI']:
                print('Parameter {} not configured for {}.'.format(par_name,gem['gatts']['sensor']))
                continue

            req_waves = [670,705]
            for i, reqw in enumerate(req_waves):
                widx,selwave = ac.shared.closest_idx(ds_waves, reqw)
                if abs(float(selwave)-float(reqw)) > 10: continue
                selds='{}_{}'.format(par_attributes['dataset'],selwave)
                required_datasets.append(selds)
                req_waves_selected.append(selwave)
            par_attributes['waves']=req_waves_selected
            if len(required_datasets) != len(req_waves): continue
            ## get data
            for di, cur_ds in enumerate(required_datasets):
                if di == 0: tmp_data = []
                if cur_ds in gem['data']:
                    cur_data  = 1.0 * gem['data'][cur_ds]
                else:
                    cur_data  = ac.shared.nc_data(gemf, cur_ds, sub=sub).data
                tmp_data.append(cur_data)
            ## compute ndci
            par_data[par_name] = (tmp_data[1]-tmp_data[0])/\
                                   (tmp_data[1]+tmp_data[0])
            par_atts[par_name] = par_attributes
            tmp_data = None
        ## end NDCI
        #############################

        #############################
        ## SLH
        if (cur_par == 'slh'):
            par_name = cur_par
            mask = True ## apply non water mask
            par_attributes = {'algorithm':'Kudela et al. 2015, SLH', 'dataset':'rhos'}
            par_attributes['standard_name']='slh'
            par_attributes['long_name']='Scattering Line Height'
            par_attributes['units']="1"
            par_attributes['reference']='Kudela et al. 2015'
            par_attributes['algorithm']=''

            required_datasets,req_waves_selected = [],[]
            ds_waves = [w for w in rhos_waves]

            ### get required datasets
            if gem['gatts']['sensor'] not in ['S2A_MSI', 'S2B_MSI']:
                print('Parameter {} not configured for {}.'.format(par_name,gem['gatts']['sensor']))
                continue

            req_waves = [670,705,780]
            for i, reqw in enumerate(req_waves):
                widx,selwave = ac.shared.closest_idx(ds_waves, reqw)
                if abs(float(selwave)-float(reqw)) > 10: continue
                selds='{}_{}'.format(par_attributes['dataset'],selwave)
                required_datasets.append(selds)
                req_waves_selected.append(selwave)
            par_attributes['waves']=req_waves_selected
            if len(required_datasets) != len(req_waves): continue
            ## get data
            for di, cur_ds in enumerate(required_datasets):
                if di == 0: tmp_data = []
                if cur_ds in gem['data']:
                    cur_data  = 1.0 * gem['data'][cur_ds]
                else:
                    cur_data  = ac.shared.nc_data(gemf, cur_ds, sub=sub).data
                tmp_data.append(cur_data)
            slh_waves = [float(ds.split('_')[1]) for ds in required_datasets]
            ratio = (tmp_data[2]-tmp_data[0]) / \
                    (slh_waves[2]+slh_waves[0])
            par_data[par_name] = tmp_data[1] - (tmp_data[0] + (ratio)*(slh_waves[1]+slh_waves[0]))
            par_atts[par_name] = par_attributes
            tmp_data = None
        ## end SLH
        #############################

        #############################
        ## OLH
        if (cur_par == 'olh'):
            par_name = cur_par
            mask = True ## apply non water mask

            par_attributes = {'algorithm':'Castagna et al. 2020'}
            par_attributes['standard_name']='olh'
            par_attributes['long_name']='Orange Line Height'
            par_attributes['units']="1"
            par_attributes['reference']='Castagna et al. 2020'
            par_attributes['algorithm']=''

            ### get required datasets
            if gem['gatts']['sensor'] != 'L8_OLI':
                print('Parameter {} not configured for {}.'.format(cur_par,gem['gatts']['sensor']))
                continue

            req_waves = [561,613,655]
            required_datasets = ['rhos_{}'.format(w) for w in req_waves]

            ## get data
            for di, cur_ds in enumerate(required_datasets):
                if di == 0: tmp_data = []
                if cur_ds in gem['data']:
                    cur_data  = 1.0 * gem['data'][cur_ds]
                else:
                    cur_data  = ac.shared.nc_data(gemf, cur_ds, sub=sub).data
                tmp_data.append(cur_data)

            ## compute parameter
            ow = (float(req_waves[2])-req_waves[1])/(float(req_waves[2])-float(req_waves[0]))
            par_data[par_name] = tmp_data[0]*ow + tmp_data[2]*(1-ow)
            par_data[par_name] = tmp_data[1]-par_data[par_name]
            tmp_data = None
            par_atts[par_name] = par_attributes
        ## end OLH
        #############################

        ## continue if parameter not computed
        if len(par_data) == 0:
            print('Parameter {} not computed'.format(cur_par))
            continue

        ## write parameters in par_data
        for cur_ds in par_data:
            ## add mask
            if mask: par_data[cur_ds][(l2_flags & flag_value)!=0] = np.nan
            ## write to NetCDF
            if verbosity > 1: print('Writing {}'.format(cur_ds))
            ac.output.nc_write(ofile, cur_ds, par_data[cur_ds], dataset_attributes=par_atts[cur_ds],
                               attributes=gem['gatts'], new=new)
            ## we can also add parameter to gem
            if return_gem:
                gem['data'][cur_ds] = par_data[cur_ds]
                gem['atts'][cur_ds] = par_atts[cur_ds]

            new = False
        par_data = None
        par_atts = None
    ## end parameter loop

    ## return data or file path
    if return_gem:
        return(gem)
    else:
        return(ofile)