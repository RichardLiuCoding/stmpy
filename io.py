import stmpy
from stmpy import matio
import numpy as np
import scipy.io as sio
import os
import re

from struct import pack, unpack, calcsize
from datetime import datetime, timedelta
from scipy.optimize import minimize


'''
STMPY I/O Version 1.0.1

Read and write common file types. 


Supported inputs:
    .spy    -   STMPY data file.
    .3ds
    .sxm
    .dat
    .nsp
    .nvi
    .nvl
    .asc

Supported ouputs:
    .spy


TO DO: 
    - Add support for .mat files
    - Rewrite load_3ds() to buffer data and improve efficiency.

History:
    2018-03-02:     HP  -   Initial commit. 
    2018-03-08:     HP  -   Added better saving for numpy data types.
'''

version = 1.0

def load(filePath, biasOffset=True, niceUnits=False):
    '''
    Loads data into python. Please include the file extension in the path.

    Currently supports formats: spy, 3ds, sxm, dat, nsp, nvi, nvl, asc. 

    For .3ds and .dat file types there is an optional flag to correct for bias offset
    that is true by default.  This does not correct for a current offset, and
    should not be used in cases where there is a significant current offset.
    Note: .mat files are supported as exports from STMView only.

    Inputs:
        filePath    - Required : Path to file including extension.
        baisOffset  - Optional : Corrects didv data for bias offset by looking
                                 for where the current is zero.
        niceUnits   - Optional : Put lock-in channel units as nS (in future
                                 will switch Z to pm, etc.)
    Returns:
        dataObject  - Custom object with attributes appropriate to the type of
                      data and containing experiment parameters in a header.
    '''
    try:
        extension = filePath.split('.')[1]
    except IndexError:
        raise IOError('Please include file extension in path.')
    loadFn = 'load_' + extension

    if extension in ['3ds', 'dat']:
        dataObject = eval(loadFn)(filePath)
        if biasOffset:
            dataObject = _correct_bias_offset(dataObject, extension)
        if niceUnits:
            dataObject = _nice_units(dataObject)
        return dataObject
    
    elif extension in ['spy', 'sxm', 'nvi', 'nvl', 'nsp', 'asc']:
        return eval(loadFn)(filePath)
    
  #  elif filePath.endswith('.mat'):
  #      raw_mat = matio.loadmat(filePath)
  #      mappy_dict = {}
  #      for key in raw_mat:
  #          try:
  #              mappy_dict[key] = matio.Mappy()
  #              mappy_dict[key].mat2mappy(raw_mat[key])
  #              print('Created channel: {:}'.format(key))
  #          except:
  #              del mappy_dict[key]
  #              print('Could not convert: {:}'.format(key))
  #      if len(mappy_dict) == 1: return mappy_dict[mappy_dict.keys()[0]]
  #      else: return mappy_dict

    else: 
        raise IOError('ERR - File type {:} not supported.'.format(extension))

def save(data, filePath, precision=None, objects=[]):
    '''Save data to file. Please include the file extension in the path.

    Currently supports: 
        .spy - STMPY generic data format. 
    '''
    try:
        extension = filePath.split('.')[1]
    except IndexError:
        raise IOError('Please include file extension in path.')
    saveFn = 'save_' + extension
    if extension in ['spy']:
        eval(saveFn)(data, filePath, precision, objects)        
    else: 
        raise IOError('ERR - File type {:} not supported.'.format(extension))



####    ____HIDDEN METHODS____    ####
def _correct_bias_offset(data, fileType):
    try:
        if fileType == 'dat':
            I = data.I
        elif fileType == '3ds':
            I = [np.mean(data.I[ix]) for ix, __ in enumerate(data.en)]
        else:
            print('ERR: Bias offset for {:} not yet implemented'.format(fileType))
            return data
        for ix, (I_low, I_high) in enumerate(zip(I[:-1], I[1:])):
            if np.sign(I_low) != np.sign(I_high):
                en_low, en_high = data.en[ix], data.en[ix+1]
                biasOffset = en_high - I_high * (en_high-en_low) / (I_high - I_low)
                data.en -= biasOffset
                break
        print('Corrected for a bias offset of {:2.2f} meV'.format(biasOffset*1000))
        return data
    except:
        print('ERR: File not in standard format for processing. Could not correct for Bias offset')
        return data

def _nice_units(data):
    '''Switch to commonly used units.

    fileType    - .3ds : Use nS for LIY and didv attribute

    History:
        2017-08-10  - HP : Comment: Missing a factor of 2, phase error not
                           justified 
    '''
    def use_nS(data):
        def chi(X):
            gFit = X * data.didv / lockInMod
            err = np.absolute(gFit - didv)
            return np.log(np.sum(err**2))
        lockInMod = float(data.header['Lock-in>Amplitude'])
        current = np.mean(data.I, axis=(1,2))
        didv = np.gradient(current) / np.gradient(data.en)
        result = minimize(chi, 1)
        data.to_nS = result.x / lockInMod * 1e9 
        data.didv *= data.to_nS
        data.LIY *= data.to_nS
        data.didvStd *= data.to_nS
        phi = np.arccos(1.0/result.x)
    
    def use_nm(data):
        fov = [float(val) for val in data.header['Scan>Scanfield'].split(';')]
        data.x = 1e9 * np.linspace(0, fov[2], data.Z.shape[1])
        data.y = 1e9 * np.linspace(0, fov[3], data.Z.shape[0])
        data.qx = stmpy.tools.fftfreq(len(data.x), data.x[-1])
        data.qy = stmpy.tools.fftfreq(len(data.y), data.y[-1])
        data.Z *= 1e9
        data._pxToNm = data.x[-1]/len(data.x)
        data._pxToInvNm = data.qx[-1]/len(data.qx)
        print('WARNING: I am not 100% sure that the q scale is right...')
    
    use_nS(data)
    use_nm(data)
    return data

def _make_attr(self, attr, names, data):
    '''
    Trys to give object an attribute from self.data by looking through
    each key in names.  It will add only the fist match, so the order of
    names dictates the preferences.

    Inputs:
        attr    - Required : Name of new attribute
        names   - Required : List of names to search for
        data    - Required : Name of a current attribute in which the new
                             attribute is stored.
    
    Returns:
        1   - If successfully added the attribute
        0   - If name is not found.

    History:
        2017-08-11  - HP : Initial commit.
        2017-08-24  - HP : Now uses grid z value for Z attribute.
    '''
    dat = getattr(self, data)
    for name in names:
       if name in dat.keys():
            setattr(self, attr, dat[name])
            return 1
    return 0



####    ____SAVE FUNCTIONS____    ####

def save_spy(data, filePath, precision=None, objects=[]):
    def write_arr(name, arr):
        if precision is not None:
            dt = arr.dtype.str
            arr = arr.astype(dt[:2] + str(precision))
        fileObj.write('ARR=' + name + '\n')
        fileObj.write(str(arr.shape) +';' + str(arr.dtype) + '\n')
        fileObj.write(bytearray(arr))
    
    def write_obj(name, obj):
        fileObj.write('OBJ=' + name + '\n')
        for name, item in obj.__dict__.items():
            write_item(name, item)
        fileObj.write(':OBJ_END:\n')

    def write_dic(name, dic):
        fileObj.write('DIC=' + name + '\n')
        for name, item in dic.items():        
            write_item(name, item)
        fileObj.write(':DIC_END:\n')

    def write_lst(name, lst):
        fileObj.write('LST=' + name + '\n')
        for ix, item in enumerate(lst):
            write_item(str(ix), item)
        fileObj.write(':LST_END:\n')

    def write_str(name, val):
        fileObj.write('STR=' + name + '\n')
        fileObj.write(bytearray(val.encode('utf-8')) + '\n')
    
    def write_num(name, val):
        fileObj.write('NUM=' + name + '\n')
        if isinstance(val, int):
            fmt = '>i'
        elif isinstance(val, float):
            fmt = '>d'
        elif isinstance(val, long):
            fmt = '>l'
        fileObj.write(fmt + pack(fmt, val))

    def write_cpx(name, val):
        fileObj.write('CPX=' + name + '\n')
        fileObj.write(pack('>f', val.real) + pack('>f', val.imag))

    def write_item(name, item):        
        if isinstance(item, np.ndarray):
            write_arr(name, item)
        elif isinstance(item, dict):
            write_dic(name, item)
        elif isinstance(item, list):
            write_lst(name, item)
        elif isinstance(item, tuple):
            print('Tuples present...')
        elif isinstance(item, file): 
            pass
        elif isinstance(item, str) or isinstance(item, unicode):
            write_str(name, item)
        elif type(item) in [int, float, long]:
            write_num(name, item)
        elif isinstance(item, complex):
            write_cpx(name, item)
        elif callable(item):
            print('WARING: Callable item not saved: {:}.'.format(name))
        elif any([isinstance(item, obj) for obj in objects]):
            write_obj(name, item)
        else:
            raise(TypeError('Item {:} {:} not supported.'.format(name, type(item))))
    
    fileObj = open(filePath, 'wb')
    fileObj.write('SPY: Stmpy I/O, Version=' + str(version) + '\n')
    objects.append(Spy)
    write_item('MAIN', data)
    fileObj.close()



####    ____LOAD FUNCTIONS____    ####

def load_spy(filePath):
    ''' Load .spy files into python''' 
    def read_arr(fileObj):
        line = fileObj.readline().strip().decode('utf-8')
        shapeStr, dtypeStr = line.split(';')
        shape = eval(shapeStr)
        dtype = np.dtype(dtypeStr)
        arr = np.fromfile(fileObj, dtype=dtype, count=np.prod(shape))
        return arr.reshape(shape)
    
    def read_obj(fileObj):
        obj = Spy()
        while True:
            line = fileObj.readline().strip().decode('utf-8')
            if line == ':OBJ_END:':
                break
            key, val = line.split('=')
            setattr(obj, val, read_item(fileObj, key))
        return obj
    
    def read_dic(fileObj):
        dic = {}
        while True:
            line = fileObj.readline().strip().decode('utf-8')
            if line == ':DIC_END:':
                break
            key, val = line.split('=')
            dic[val] = read_item(fileObj, key)
        return dic
    
    def read_lst(fileObj):
        lst = []
        while True:
            line = fileObj.readline().strip().decode('utf-8')
            if line == ':LST_END:':
                break
            key, val = line.split('=')
            lst.append(read_item(fileObj, key))
        return lst
    
    def read_str(fileObj):
        return fileObj.readline().strip().decode('utf-8')
    
    def read_num(fileObj):
        fmt = fileObj.read(2)
        num = unpack(fmt, fileObj.read(calcsize(fmt)))[0]
        return num
    
    def read_cpx(fileObj):
        real = unpack('>f', fileObj.read(4))[0]
        imag = unpack('>f', fileObj.read(4))[0]
        return complex(real, imag)
    
    def read_item(fileObj, key):
        if key == 'ARR':
            item = read_arr(fileObj)
        elif key == 'OBJ':
            item = read_obj(fileObj)
        elif key == 'DIC': 
            item = read_dic(fileObj)
        elif key == 'LST':
            item = read_lst(fileObj)
        elif key == 'STR':
            item = read_str(fileObj)
        elif key == 'NUM':
            item = read_num(fileObj)
        elif key == 'CPX':
            item = read_cpx(fileObj)
        else:
            raise(TypeError(
                'File contains unsupported format: {:}'.format(key)))
        return item

    fileObj = open(filePath, 'rb')
    fileObj.seek(0,2)
    fileSize = fileObj.tell()
    fileObj.seek(0)
    name, version = fileObj.readline().strip().decode('utf-8').split('=')
    if version < 1.0:
        raise(TypeError('Version {:} files not supported'.format(version)))
    while fileObj.tell() < fileSize:
        line = fileObj.readline().strip().decode('utf-8')
        key, val = line.split('=')
        item = read_item(fileObj, key)
    fileObj.close()
    return item


def load_3ds(filePath):
    '''Load Nanonis 3ds into python.'''
    try: 
        fileObj = open(filePath, 'rb')
    except:  
        raise NameError('File not found.')
    self = Spy()
    self.header={}
    while True:
        line = fileObj.readline().strip().decode('utf-8')
        if line == ':HEADER_END:': 
            break
        splitLine = line.split('=')
        self.header[splitLine[0]] = splitLine[1]
    self._info = {'params'	: int(self.header['# Parameters (4 byte)']),
                'paramName'	: self.header['Fixed parameters'][1:-1].split(';') +
                              self.header['Experiment parameters'][1:-1].split(';'),
                'channels'	: self.header['Channels'][1:-1].split(';'),
                'points'	: int(self.header['Points']),
                'sizex' 	: int(self.header['Grid dim'][1:-1].split(' x ')[0]),
                'sizey'	: int(self.header['Grid dim'][1:-1].split(' x ')[1]),
                'dataStart'	: fileObj.tell()
                 }
    self.grid = {}; self.scan = {}
    for channel in self._info['channels']:
        self.grid[channel] = np.zeros(
                [self._info['points'], self._info['sizey'], self._info['sizex']])
    for channel in self._info['paramName']:
        self.scan[channel] = np.zeros([self._info['sizey'], self._info['sizex']])

    try:
        for iy in range(self._info['sizey']):
            for ix in range(self._info['sizex']):
                for channel in self._info['paramName']:
                    value = unpack('>f',fileObj.read(4))[0]
                    self.scan[channel][iy,ix] = value

                for channel in self._info['channels']:
                    for ie in range(self._info['points']):
                        value = unpack('>f',fileObj.read(4))[0]
                        self.grid[channel][ie,iy,ix] = value
    except:
        print('WARNING: Data set is not complete.')

    dataRead = fileObj.tell()
    fileObj.read()
    allData = fileObj.tell()
    if dataRead == allData: 
        print('File import successful.')
    else: 
        print('ERR: Did not reach end of file.')
    fileObj.close()
    
    LIYNames =  ['LIY 1 omega (A)', 'LIY 1 omega [AVG] (A)']
    if _make_attr(self, 'LIY', LIYNames, 'grid'):
        self.didv = np.mean(self.LIY, axis=(1,2))
        self.didvStd = np.std(self.LIY, axis=(1,2))
    else:
        print('ERR: LIY AVG channel not found, resort to manual ' + 
              'definitions.  Found channels:\n {:}'.format(self.data.keys()))
    
    _make_attr(self, 'I',  ['Current (A)', 'Current [AVG] (A)'], 'grid')
    if _make_attr(self, 'Z',  ['Z (m)', 'Z [AVG] (m)'], 'grid'):
        self.Z = self.Z[0]
    else:
        _make_attr(self, 'Z', ['Scan:Z (m)'], 'scan')
        print('WARNING: Using scan channel for Z attribute.')
    try:     
        self.en = np.mean(self.grid['Bias [AVG] (V)'], axis=(1,2))
    except KeyError:
        print('WARNING: Assuming energy layers are evenly spaced.')
        self.en = np.linspace(self.scan['Sweep Start'].flatten()[0],
                              self.scan['Sweep End'].flatten()[0],
                              self._info['points'])

    return self


def load_sxm(filePath):
    ''' Load Nanonis SXM files into python. '''
    try: 
        fileObj = open(filePath, 'rb')
    except:  
        raise NameError('File not found.')
    self = Spy()
    self.header={}
    s1 = fileObj.readline().decode('utf-8')
    if not re.match(':NANONIS_VERSION:', s1):
        raise NameError('The file %s does not have the Nanonis SXM'.format(filePath))
    self.header['version'] = int(fileObj.readline())
    while True:
        line = fileObj.readline().strip().decode('utf-8')
        if re.match('^:.*:$', line):
            tagname = line[1:-1]
        else:
            if 'Z-CONTROLLER' == tagname:
                keys = line.split('\t')
                values = fileObj.readline().strip().decode('utf-8').split('\t')
                self.header['z-controller'] = dict(zip(keys, values))
            elif tagname in ('BIAS', 'REC_TEMP', 'ACQ_TIME', 'SCAN_ANGLE'):
                self.header[tagname.lower()] = float(line)
            elif tagname in ('SCAN_PIXELS', 'SCAN_TIME', 'SCAN_RANGE', 'SCAN_OFFSET'):
                self.header[tagname.lower()] = [ float(i) for i in re.split('\s+', line) ]
            elif 'DATA_INFO' == tagname:
                if 1 == self.header['version']:
                    keys = re.split('\s\s+',line)
                else:
                    keys = line.split('\t')
                self.header['data_info'] = []
                while True:
                    line = fileObj.readline().strip().decode('utf-8')
                    if not line:
                        break
                    values = line.strip().split('\t')
                    self.header['data_info'].append(dict(zip(keys, values)))
            elif tagname in ('SCANIT_TYPE','REC_DATE', 'REC_TIME', 'SCAN_FILE', 'SCAN_DIR'):
                self.header[tagname.lower()] = line
            elif 'SCANIT_END' == tagname:
                break
            else:
                if tagname.lower() not in self.header:
                    self.header[tagname.lower()] = line
                else:
                    self.header[tagname.lower()] += '\n' + line
    if 1 == self.header['version']:
        self.header['scan_pixels'].reverse()
    fileObj.readline()
    fileObj.read(2) # Need to read the byte \x1A\x04, before reading data
    size = int(self.header['scan_pixels'][0] * self.header['scan_pixels'][1] * 4)
    shape = [int(val) for val in self.header['scan_pixels']]
    self.channels = {}
    for channel in self.header['data_info']:
        if channel['Direction'] == 'both':
            self.channels[channel['Name'] + '_Fwd'] = np.ndarray(
                    shape=shape[::-1], dtype='>f', buffer=fileObj.read(size))
            self.channels[channel['Name'] + '_Bkd'] = np.ndarray(
                    shape=shape[::-1], dtype='>f', buffer=fileObj.read(size))
        else:
            self.channels[channel['Name'] + channel['Direction']] = np.ndarray(
                    shape=shape, dtype='>f', buffer=fileObj.read(size))
    try:
        self.Z = self.channels['Z_Fwd']
        self.I = self.channels['Current_Fwd']
        self.LIY = self.channels['LIY_1_omega_Fwd']
    except KeyError: print('WARNING:  Could not create standard attributes, look in channels instead.')
    fileObj.close()
    return self


def load_dat(filePath):
    ''' Load Nanonis SXM files into python. '''
    try: 
        fileObj = open(filePath, 'rb')
    except:  
        raise NameError('File not found.')
    self = Spy()
    self.header={}
    self.channels = {}
    while True:
        line = fileObj.readline()
        splitLine = line.split('\t')
        if line[0:6] == '[DATA]': 
            break
        elif line.rstrip() != '': 
            self.header[splitLine[0]] = splitLine[1]
    channels = fileObj.readline().rstrip().split('\t')
    allData = []
    for line in fileObj:
        line = line.rstrip().split('\t')
        allData.append(np.array(line, dtype=float))
    allData = np.array(allData)
    for ix, channel in enumerate(channels):
        self.channels[channel] = allData[:,ix]
    dataRead = fileObj.tell()
    fileObj.read()
    finalRead = fileObj.tell()
    if dataRead == finalRead: 
        print('File import successful.')
    else: 
        print('ERR: Did not reach end of file.')
    fileObj.close()
    _make_attr(self, 'didv', 
            ['LIY 1 omega (A)', 'LIY 1 omega [AVG] (A)'], 'channels')
    _make_attr(self, 'I', ['Current (A)', 'Current [AVG] (A)'],
    'channels')
    _make_attr(self, 'en', ['Bias (V)', 'Bias calc (V)'], 'channels')
    if 'LIY 1 omega [00001] (A)' in self.channels.keys():
        sweeps = int(self.header['Bias Spectroscopy>Number of sweeps'])
        self.LIY = np.zeros([len(self.en), sweeps])
        for ix in range(1, sweeps+1):
            s = str(ix).zfill(5)
            self.LIY[:,ix-1] = self.channels['LIY 1 omega [' + s + '] (A)']
        self.didvStd = np.std(self.LIY, axis=1)
    return self


def load_nsp(filePath):
    '''UNTESTED - Load Nanonis Long Term Specturm into python.'''
    try: 
        fileObj = open(filePath, 'rb')
    except:  
        raise NameError('File not found.')
    self = Spy()
    self.header={}
    while True:
        line = fileObj.readline().strip().decode('utf-8')
        if line == ':HEADER_END:': 
            break
        elif re.match('^:.*:$', line):
            tagname = line[1:-1]
        else:
            try:
                self.header[tagname] = int(line.split('\t')[0])
            except:
                self.header[tagname] = line.split('\t')[0]

    self.freq = np.linspace(0, 
            np.round(float(self.header['DATASIZECOLS'])*float(self.header['DELTA_f'])),
            float(self.header['DATASIZECOLS']))
    
    self.start = datetime.strptime(self.header['START_DATE'] + 
            self.header['START_TIME'],'%d.%m.%Y%H:%M:%S')
    self.end = datetime.strptime(self.header['END_DATE'] + 
            self.header['END_TIME'],'%d.%m.%Y%H:%M:%S')
    self.time = np.linspace(0, (self.end - self.start).total_seconds(), 
            int(self.header['DATASIZEROWS']))
    self.data = np.zeros([int(self.header['DATASIZEROWS']), int(self.header['DATASIZECOLS'])])
    fileObj.read(2) #first two bytes are not data
    try:
        for ix in range(int(self.header['DATASIZEROWS'])):
            for iy in range(int(self.header['DATASIZECOLS'])):
                value = unpack('>f',fileObj.read(4))[0]
                self.data[ix,iy] = value
    except:
        print('ERR: Data set is not complete')
    fileObj.close()
    if self.header['SIGNAL'] == 'Current (A)':
        self.fftI = self.data.T
    elif self.header['SIGNAL'] == 'InternalGeophone (V)':
        self.fftV = self.data.T
    else:
        self.fftSignal = self.data.T
    return self


def load_nvi(filePath):
    '''UNTESTED - Load NISTview image data into python. '''
    nviData = sio.readsav(filePath)
    self = Spy()
    self._raw = nviData['imagetosave']
    self.map = self._raw.currentdata[0]
    self.header = {name:self._raw.header[0][name][0] for name in self._raw.header[0].dtype.names}
    self.info = {'FILENAME'    : self._raw.filename[0],
                 'FILSIZE'     : int(self._raw.header[0].filesize[0]),
                 'CHANNELS'    : self._raw.header[0].scan_channels[0],
                 'XSIZE'       : self._raw.xsize[0],
                 'YSIZE'       : self._raw.ysize[0],
                 'TEMPERATURE' : self._raw.header[0].temperature[0],
                 'LOCKIN_AMPLITUDE' : self._raw.header[0].lockin_amplitude[0],
                 'LOCKIN_FREQUENCY' : self._raw.header[0].lockin_frequency[0],
                 'DATE'        : self._raw.header[0].date[0],
                 'TIME'        : self._raw.header[0].time[0],
                 'BIAS_SETPOINT'    : self._raw.header[0].bias_setpoint[0],
                 'BIAS_OFFSET' : self._raw.header[0].bias_offset[0],
                 'BFIELD'      : self._raw.header[0].bfield[0],
                 'ZUNITS'      : self._raw.zunits[0],
					}
    return self


def load_nvl(filePath):
    '''UNTESTED - Load NISTview layer data into python. '''
    nvlData = sio.readsav(filePath)
    self = Spy()
    self._raw = nvlData['savestructure']
    self.en = self._raw.energies[0]
    self.map = self._raw.fwddata[0]
    self.ave = [np.mean(layer) for layer in self.map]
    self.header = {name:self._raw.header[0][name][0] for name in self._raw.header[0].dtype.names}
    for name in self._raw.dtype.names:
        if name not in self.header.keys():
            self.header[name] = self._raw[name][0]
    return self


def load_asc(filePath):
    '''UNTESTED - Load ASCII files into python.'''
    try: 
        fileObj = open(filePath, 'rb')
    except:  
        raise NameError('File not found.')
    self = Spy()
    header= {}
    channels = {}
    while True:
        line = fileObj.readline().rstrip()
        if line is '':
            break
        splitLine = line.split(':')
        header[splitLine[0]] = splitLine[1]
    channelNames = fileObj.readline().rstrip().split('      ')
    for chn in channelNames:
        channels[chn] = []
    for data in fileObj.readlines():
        dsplit = data.rstrip().split('   ')
        dfloat = [float(val) for val in dsplit]
        for chn, val in zip(channelNames, dfloat):
            channels[chn] += [val]
    for chn in channelNames:
        channels[chn] = np.array(channels[chn])
    if len(channelNames) is 2:
        self.x = channels[channelNames[0]]
        self.y = channels[channelNames[1]]
    self.header = header
    self.channels = channels
    fileObj.close()
    return self

    
####    ____CLASS DEFINITIONS____   ####

class Spy(object):
    def __init__(self):
        pass
