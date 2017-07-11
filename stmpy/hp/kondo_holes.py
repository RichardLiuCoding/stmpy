import stmpy
import numpy as np
from scipy.optimize import minimize
import pylab as plt


def cubic_gap(x, y, threshold=0):
    '''
    Find phenomenological hybridization gap by the difference between cubic
    inflection points.  Splits data into high energy and low energy parts and
    fits a cubic to each. Returns the difference between the inflection points. 

    Inputs:
        x       - Required : A 1D numpy array containing x values (usually en)
        y       - Required : A 1D numpy array containing y values (usually
                             didv).
        threshold - Optional : Integer that alters the splitting point. The
                               splitting points are (max - threshold) and 
                               (min + threshold).

    Returns:
        gapValue - The difference between the x values of the inflection
                   points.

    History:
        2017-07-11  - HP : Initial commit.
    '''
    def find_inflection(x, y, deg=3):
        pFit = np.polyfit(x, y, deg)
        infl = -1.0/3 * pFit[1]/pFit[0]
        return infl
    xLow = x[:argmax(y)-int(threshold)]
    yLow = y[:argmax(y)-int(threshold)]
    xHig = x[argmin(y)+int(threshold):]
    yHig = y[argmin(y)+int(threshold):]
    return find_inflection(xHig, yHig, 3) - find_inflection(xLow, yLow, 3)


def cubic_gapmap(LIY, en, **kwarg):
    '''Computes a cubic gap for each dIdV measurement in a DOS-map.
    
    Inputs:
        LIY - Required : 3D numpy array containing the data.
        en  - Required : 1D numpy array containing energy values. 
        **kwarg        : Keyword arguments passed to cubic_gap()

    Returns:
        gapmap - A 2D numpy array containing the size of the cubic gap at each
                 point 

    History:
        2017-06-18  - Initial commit.
    '''
    gapmap = zeros([LIY.shape[1], LIY.shape[2]])
    for iy in range(LIY.shape[1]):
        for ix in range(LIY.shape[2]):
            gapmap[iy,ix] = inflection_gap(en, LIY[:,iy,ix], **kwarg)
        stmpy.tools.print_progress_bar(iy, LIY.shape[1]-1, fill='>')
    return gapmap


def fano(E, g, ef, q, a, b, c):
    '''
    Calculate Fano lineshapes describing the interaction of a disctrete
    state with a background continuum. See http://doi.org/10.1038/nature09073
    for detail of the model.  

    Inputs:
        E   - Required : 1D numpy array containing x values for calculation.
        g   - Required : Float. Gamma parameter in Fano model which describes
                         the lifetime of the discrete state.  This is
                         proportional to the interaction strength. 
        ef  - Required : Float. Energy level of discrete state.
        q   - Required : Float. Ratio of tunneling probabilities.
        a   - Required : Float. Scaling factor for units conversion.
        b   - Required : Float. Additional linear slope.
        c   - Required : Float. Additional offset value.

    Returns:
        fanoCalc - a 1D numpy array containing the calculation.
    
    History:
        2017-06-18  - HP : Initial commit.   
    '''
    EPrime = 2.0*(E - ef)/g
    y = (q+EPrime)**2 / (EPrime**2 + 1.0)
    return a*y + b*E + c


def fano_fit(xData, yData, X0=[8.75,-3.6,-0.6,-5.6,0.04,10]):
    '''Fit Fano model to data.  
    See help(stmpy.hp.kondo_holes.fano) for details. 
    
    Inputs:
        xData   - Required : 1D numpy array containing X values.
        yData   - Required : 1D numpy array containing Y values.
        X0      - Optional : 1D numpy array containing the initial guess for
                             Fano parameters in the form: 
                             [E, g, ef, q, a, b, c]
    
    Returns: 
        result - Scipy.optimize.minimize.OptimizeResult object. Important
                 attribute is x, the solution array. See scipy docs for more
                 info.

    History:
        2017-06-18  - HP : Initial commit.
    '''
    def chi(X):
        yFit = fano(xData, X[0], X[1], X[2], X[3], X[4], X[5])
        err = np.absolute(yData - yFit)
        return np.log(np.sum(err**2))
    result = minimize(chi, X0)
    return result


def fano_gapmap(LIY, en): 
    '''Computes a Fano fit to each dIdV measurement in a DOS-map.
    See help(stmpy.hp.kondo_holes.fano_fit) for details.

    Inputs:
        LIY - Required : 3D numpy array containing the data.
        en  - Required : 1D numpy array containing energy values. 

    Returns:
        gapmap - A 3D numpy array containing the fit parameters at each spatial
                 point. The fit parameters are in the order: g, ef, q, a, b, c.
                 i.e. gapmap[0] is a spatial map of hybridization strength. 
    
    History:
        2017-06-18  - Initial commit.
    '''
    gapmap = np.zeros([6, LIY.shape[1], LIY.shape[2]])
    for iy in range(LIY.shape[1]):
        for ix in range(LIY.shape[2]):
            result = fano_fit(en, LIY[:,iy,ix])
            gapmap[:,iy,ix] = result.x
        stmpy.tools.print_progress_bar(iy, LIY.shape[1]-1, fill='>')
    return gapmap
