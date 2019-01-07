"""
NUFFT CPU classes
=======================================
"""

from __future__ import absolute_import
import numpy
import scipy.sparse
import numpy.fft
import scipy.signal
import scipy.linalg
import scipy.special

from ..src._helper import helper, helper1


def push_cuda_context(hsa_method):
    """
    Decorator: Push cude context to the top of the stack for current use
    Add @push_cuda_context before the methods of NUFFT_hsa()
    """
    
    def wrapper(*args, **kwargs):
        try:
            args[0].thr._context.push()
        except:
            pass     
        return hsa_method(*args, **kwargs)
    return wrapper

class NUFFT_cpu:
    """
    Class NUFFT_cpu
   """    
    def __init__(self):
        """
        Constructor.
        
        :param None:
        :type None: Python NoneType
        :return: NUFFT: the pynufft_hsa.NUFFT instance
        :rtype: NUFFT: the pynufft_hsa.NUFFT class
        :Example:

        >>> import pynufft
        >>> NufftObj = pynufft.NUFFT_cpu()
        """        
        self.dtype=numpy.complex64
        self.debug = 0  # debug
        pass

    def plan(self, om, Nd, Kd, Jd, ft_axes = None, batch = None):
        """
        Plan the NUFFT_cpu object with the provided geometry.
        
        :param om: The M off-grid locations in the frequency domain, which is normalized between [-pi, pi]
        :param Nd: The matrix size of equispaced image. Example: Nd=(256,256) for a 2D image; Nd = (128,128,128) for a 3D image
        :param Kd: The matrix size of the oversampled frequency grid. Example: Kd=(512,512) for 2D image; Kd = (256,256,256) for a 3D image
        :param Jd: The interpolator size. Example: Jd=(6,6) for 2D image; Jd = (6,6,6) for a 3D image
        :param ft_axes: (Optional) The axes for Fourier transform. The default is all axes if None is given.
        :param batch: (Optional) Batch mode. If batch is provided, the last appended axes is the number of identical NUFFT to be transformed. The default is None.
        :type om: numpy.float array, matrix size = M * ndims
        :type Nd: tuple, ndims integer elements. 
        :type Kd: tuple, ndims integer elements. 
        :type Jd: tuple, ndims integer elements. 
        :type ft_axes: None, or tuple with optional integer elements.
        :type batch: None, or integer
        :returns: 0
        :rtype: int, float
        :Example:

        >>> import pynufft
        >>> NufftObj = pynufft.NUFFT_cpu()
        >>> NufftObj.plan(om, Nd, Kd, Jd) 
        
        or 
        
        >>> NufftObj.plan(om, Nd, Kd, Jd, ft_axes, batch)
        
        """         
        

#         n_shift = tuple(0*x for x in Nd)
        self.ndims = len(Nd) # dimension
        if ft_axes is None:
            ft_axes = range(0, self.ndims)
        self.ft_axes = ft_axes
#     
        self.st = helper.plan(om, Nd, Kd, Jd, ft_axes = ft_axes, format = 'CSR')
#         st_tmp = helper.plan0(om, Nd, Kd, Jd)
#         if self.debug is 1:
#             print('error between current and old interpolators=', scipy.sparse.linalg.norm(self.st['p'] - st_tmp['p'])/scipy.sparse.linalg.norm(self.st['p']))
#             print('error between current and old scaling=', numpy.linalg.norm(self.st['sn'] - st_tmp['sn']))
        
        self.Nd = self.st['Nd']  # backup
        self.Kd = self.st['Kd']
        self.sn = numpy.asarray(self.st['sn'].astype(self.dtype)  ,order='C')# backup
            
        if batch is None: # single-coil
            self.parallel_flag = 0
            self.batch = 1
#             self.sense = None
#             self.sense = numpy.ones( Nd, dtype = self.dtype, order='C')
            
#             self.Reps = numpy.uint32( 1)
#             print('self.Reps = ', self.Reps ,'self.parallel_flag=', self.parallel_flag)
        else: # multi-coil
            self.parallel_flag = 1
            self.batch = batch
            
#             self.Reps = numpy.uint32( coil_sense.shape[-1])
#             print('self.Reps = ', self.Reps ,'self.parallel_flag=', self.parallel_flag)
        if self.parallel_flag is 1:
            self.multi_Nd =   self.Nd + (self.batch, )
            self.multi_Kd =   self.Kd + (self.batch, )
            self.multi_M =   (self.st['M'], )+ (self.batch, )
            self.multi_prodKd = (numpy.prod(self.Kd), self.batch)
            self.sn = numpy.reshape(self.sn, self.Nd + (1,))

        elif self.parallel_flag is 0:
            self.multi_Nd =   self.Nd# + (self.Reps, )
            self.multi_Kd =   self.Kd #+ (self.Reps, )
            self.multi_M =   (self.st['M'], )
            self.multi_prodKd = (numpy.prod(self.Kd), )

        # Calculate the density compensation function
        self.sp = self.st['p'].copy().tocsr()
        self.spH = (self.st['p'].getH().copy()).tocsr()        
        self.Kdprod = numpy.int32(numpy.prod(self.st['Kd']))
        self.Jdprod = numpy.int32(numpy.prod(self.st['Jd']))
        del self.st['p'], self.st['sn']
#         self._precompute_sp()        
#         del self.st['p0'] 
        self.NdCPUorder, self.KdCPUorder, self.nelem =     helper.preindex_copy(self.st['Nd'], self.st['Kd'])

        
        return 0
        
#         print('untrimmed',self.st['pHp'].nnz)
#         self.truncate_selfadjoint(1e-1)
#         print('trimmed', self.st['pHp'].nnz)
 
    def _precompute_sp(self):
        """

        Private: Precompute adjoint (gridding) and Toepitz interpolation matrix.
        
        :param None: 
        :type None: Python Nonetype
        :return: self: instance
        """
        try:
            W0 = numpy.ones((self.st['M'],), dtype = numpy.complex64)
            W = self.xx2k(self.adjoint(W0))
            self.W = (W*W.conj())**0.5
            del W0
            del W
        except:
            print("errors occur in self.precompute_sp()")
            raise


    def solve(self,y, solver=None, *args, **kwargs):
        """
        Solve NUFFT_cpu
        
        :param y: data, numpy array, (M,) size
        :param solver: could be 'cg', 'L1TVOLS', 'L1TVLAD' 
        :param maxiter: the number of iterations
        :type y: numpy array, dtype = numpy.complex64
        :type solver: string
        :type maxiter: int
        :return: numpy array with size Nd
        """        
        from ..linalg.solve_cpu import solve
#         if self.parallel_flag is 1:
#             x2 = numpy.empty(self.multi_Nd, dtype = self.dtype)
#             for bat in range(0, self.batch):
#                 x2[..., bat] = solve(self, y[:,bat], solver, *args, **kwargs)
#         else:
        x2 = solve(self,  y,  solver, *args, **kwargs)
        return x2#solve(self,  y,  solver, *args, **kwargs)

    def forward(self, x):
        """
        Forward NUFFT on CPU
        
        :param x: The input numpy array, with the size of Nd or Nd + (batch,)
        :type: numpy array with the dtype of numpy.complex64
        :return: y: The output numpy array, with the size of (M,) or (M, batch)
        :rtype: numpy array with the dtype of numpy.complex64
        """
        y = self.k2y(self.xx2k(self.x2xx(x)))

        return y

    def adjoint(self, y):
        """
        Adjoint NUFFT on CPU
        
        :param y: The input numpy array, with the size of (M,) or (M, batch) 
        :type: numpy array with the dtype of numpy.complex64
        :return: x: The output numpy array, with the size of Nd or Nd + (batch, )
        :rtype: numpy array with the dtype of numpy.complex64
        """     
        x = self.xx2x(self.k2xx(self.y2k(y)))

        return x

    def selfadjoint(self, x):
        """
        selfadjoint NUFFT (Teplitz) on CPU
        
        :param x: The input numpy array, with size=Nd
        :type: numpy array with dtype =numpy.complex64
        :return: x: The output numpy array, with size=Nd
        :rtype: numpy array with dtype =numpy.complex64
        """       
#         x2 = self.adjoint(self.forward(x))
        
        x2 = self.xx2x(self.k2xx(self.k2y2k(self.xx2k(self.x2xx(x)))))
#         x2 = self.k2xx(self.W*self.xx2k(x))
#         x2 = self.k2xx(self.k2y2k(self.xx2k(x)))
        
        return x2
    def selfadjoint2(self, x):
        try:
            x2 = self.k2xx(self.W*self.xx2k(x))
        except:
            self._precompute_sp()
            x2 = self.k2xx(self.W*self.xx2k(x))
        return x2
    
    def x2xx(self, x):
        """
        Private: Scaling on CPU
        Inplace multiplication of self.x_Nd by the scaling factor self.sn.
        """    
        xx = x * self.sn
        return xx

    def xx2k(self, xx):
        """
        Private: oversampled FFT on CPU
        
        Firstly, zeroing the self.k_Kd array
        Second, copy self.x_Nd array to self.k_Kd array by cSelect
        Third: inplace FFT
        """
#         dd = numpy.size(self.Kd)      
#         output_x = numpy.zeros(self.Kd, dtype=self.dtype,order='C')
        output_x = numpy.zeros(self.multi_Kd, dtype=self.dtype,order='C')
        
        for bat in range(0, self.batch):
            output_x.ravel()[self.KdCPUorder*self.batch + bat]=xx.ravel()[self.NdCPUorder*self.batch + bat]
        
        k = numpy.fft.fftn(output_x, axes = self.ft_axes)
#         k = numpy.fft.fftn(a=xx, s=tuple(self.Kd[ax] for ax in self.ft_axes), axes = self.ft_axes)
        return k
    
    def k2vec(self,k):
        k_vec = numpy.reshape(k, self.multi_prodKd, order='C')
        return k_vec
    
    def vec2y(self,k_vec):
        '''
        gridding: 
        '''
        y = self.sp.dot(k_vec)
#         y = self.st['ell'].spmv(k_vec)
        
        return y
    def k2y(self, k):
        """
        Private: interpolation by the Sparse Matrix-Vector Multiplication
        """
        y = self.vec2y(self.k2vec(k)) #numpy.reshape(self.st['p'].dot(Xk), (self.st['M'], ), order='F')
        
        return y
    def y2vec(self, y):
        '''
       regridding non-uniform data, (unsorted vector)
        '''
#         k_vec = self.st['p'].getH().dot(y)
        k_vec = self.spH.dot(y)
#         k_vec = self.st['ell'].spmvH(y)
        
        return k_vec
    def vec2k(self, k_vec):
        '''
        Sorting the vector to k-spectrum Kd array
        '''
        k = numpy.reshape(k_vec, self.multi_Kd, order='C')
        
        return k
    
    def y2k(self, y):
        """
        Private: gridding by the Sparse Matrix-Vector Multiplication
        """
        k_vec = self.y2vec(y)
        k = self.vec2k(k_vec)
        return k

    def k2xx(self, k):
        """
        Private: the inverse FFT and image cropping (which is the reverse of _xx2k() method)
        """
#         dd = numpy.size(self.Kd)
        
        k = numpy.fft.ifftn(k, axes = self.ft_axes)
        xx= numpy.zeros(self.multi_Nd,dtype=self.dtype, order='C')
        for bat in range(0, self.batch):
            xx.ravel()[self.NdCPUorder*self.batch + bat]=k.ravel()[self.KdCPUorder*self.batch + bat]
#         xx = xx[crop_slice_ind(self.Nd)]
        return xx

    def xx2x(self, xx):
        """
        Private: rescaling, which is identical to the  _x2xx() method
        """
        x = self.x2xx(xx)
        return x
    
    def k2y2k_single(self, k):
        """
        Private: the integrated interpolation-gridding by the Sparse Matrix-Vector Multiplication
        """

#         Xk = self.k2vec(k)
        y = self.sp.dot(k.ravel())
        k2 = self.spH.dot(y)
        k2 = numpy.reshape(k2, self.Kd, order='C')
#         k = self.spHsp.dot(Xk)
#         k = self.spH.dot(self.sp.dot(Xk))
#         k = self.y2vec(self.vec2y(Xk))
#         k = self.vec2k(k)
        return k2
    
    def k2y2k(self, k):
        """
        Private: the integrated interpolation-gridding by the Sparse Matrix-Vector Multiplication
        """

        Xk = self.k2vec(k)
         
#         k = self.spHsp.dot(Xk)
#         k = self.spH.dot(self.sp.dot(Xk))
        k = self.y2vec(self.vec2y(Xk))
        k = self.vec2k(k)
        return k


class NUFFT_excalibur(NUFFT_cpu):
    """
    Class NUFFT_hsa for heterogeneous systems.
   """

    def __init__(self):
        """
        Constructor.
        
        :param None:
        :type None: Python NoneType
        :return: NUFFT: the pynufft_hsa.NUFFT instance
        :rtype: NUFFT: the pynufft_hsa.NUFFT class
        :Example:

        >>> import pynufft
        >>> NufftObj = pynufft.NUFFT_hsa()
        """
        
        pass
        NUFFT_cpu.__init__(self)

    def plan1(self, om, Nd, Kd, Jd, ft_axes, coil_sense):
        """
        Design the min-max interpolator.
        
        :param om: The M off-grid locations in the frequency domain. Normalized between [-pi, pi]
        :param Nd: The matrix size of equispaced image. Example: Nd=(256,256) for a 2D image; Nd = (128,128,128) for a 3D image
        :param Kd: The matrix size of the oversampled frequency grid. Example: Kd=(512,512) for 2D image; Kd = (256,256,256) for a 3D image
        :param Jd: The interpolator size. Example: Jd=(6,6) for 2D image; Jd = (6,6,6) for a 3D image
        :type om: numpy.float array, matrix size = M * ndims
        :type Nd: tuple, ndims integer elements. 
        :type Kd: tuple, ndims integer elements. 
        :type Jd: tuple, ndims integer elements. 
        :returns: 0
        :rtype: int, float
        :Example:

        >>> import pynufft
        >>> NufftObj = pynufft.NUFFT_cpu()
        >>> NufftObj.plan(om, Nd, Kd, Jd) 
        
        """         
        

#         n_shift = tuple(0*x for x in Nd)
        self.ndims = len(Nd) # dimension
        if ft_axes is None:
            ft_axes = range(0, self.ndims)
        self.ft_axes = ft_axes
#     
        self.st = helper1.plan1(om, Nd, Kd, Jd, ft_axes,  coil_sense)
#         st_tmp = helper.plan0(om, Nd, Kd, Jd)
        if self.debug is 1:
            print('error between current and old interpolators=', scipy.sparse.linalg.norm(self.st['p'] - st_tmp['p'])/scipy.sparse.linalg.norm(self.st['p']))
            print('error between current and old scaling=', numpy.linalg.norm(self.st['sn'] - st_tmp['sn']))
        
        self.Nd = self.st['Nd']  # backup
        self.Kd = self.st['Kd']
        self.sn = numpy.asarray(self.st['sn'].astype(self.dtype)  ,order='C')# backup
            
        
        # Calculate the density compensation function
        self.sp = self.st['p'].copy().tocsr()
        self.spH = (self.st['p'].getH().copy()).tocsr()        
        self.Kdprod = numpy.int32(numpy.prod(self.st['Kd']))
        self.Jdprod = numpy.int32(numpy.prod(self.st['Jd']))
        del self.st['p'], self.st['sn']
#         self._precompute_sp()        
#         del self.st['p0'] 
        self.NdCPUorder, self.KdCPUorder, self.nelem =     helper.preindex_copy(self.st['Nd'], self.st['Kd'])
        return 0