"""
Class NUFFT on Numpy/Scipy
=================================
"""

import numpy
import scipy.sparse
import numpy.fft
import scipy.signal
import scipy.linalg
import scipy.special

# from .... import src
from .._helper.helper import *

class NUFFT:
    """
    The class NUFFT belongs to pynufft, which computes Non-Uniform Fast Fourier Transform (NUFFT) in Numpy/Scipy.
   """    
    def __init__(self):
        """
        Constructor.
        
        :param None:
        :type None: Python NoneType
        :return: NUFFT: the pynufft_hsa.NUFFT instance
        :rtype: NUFFT: the pynufft_hsa.NUFFT class
        :Example:

        >>> import pynufft.pynufft
        >>> NufftObj = pynufft.pynufft.NUFFT_cpu()


        .. note:: requires plan() 
        .. seealso:: :method:`plan()' 
        .. todo:: test 3D case
        """        
        self.dtype=numpy.complex64
        pass

    def plan(self, om, Nd, Kd, Jd):
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
        >>> NufftObj = pynufft_hsa.NUFFT()
        >>> NufftObj.plan(om, Nd, Kd, Jd) 
        
        """         
        self.debug = 0  # debug

        n_shift = tuple(0*x for x in Nd)
        self.st = plan(om, Nd, Kd, Jd)
        
        self.Nd = self.st['Nd']  # backup
        self.Kd = self.st['Kd']
        self.sn = numpy.asarray(self.st['sn'].astype(dtype)  ,order='C')# backup
        self.ndims = len(self.Nd) # dimension
        self._linear_phase(n_shift)  # calculate the linear phase thing
        
        # Calculate the density compensation function
        self._precompute_sp()
        del self.st['p'], self.st['sn']
        del self.st['p0'] 
        self.NdCPUorder, self.KdCPUorder, self.nelem =     preindex_copy(self.st['Nd'], self.st['Kd'])
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
            self.sp = self.st['p']
            self.spH = (self.st['p'].getH().copy()).tocsr()
            self.spHsp =self.st['p'].getH().dot(self.st['p']).tocsr()
        except:
            print("errors occur in self.precompute_sp()")
            raise
#         self.truncate_selfadjoint( 1e-2)

    def _matvec(self, x_vec):
        """
        (To be tested): dot operation provided for scipy.sparse.linalg
        wrapper of self.forward()
        """
        
        x2 = numpy.reshape(x_vec, self.Nd, order='F')
        
        return self.forward(x2) 

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
        from .._nonlin.solve_cpu import solve
        return solve(self,  y,  solver, *args, **kwargs)

    
    def _pipe_density(self,maxiter):
        '''
        Create the density function by iterative solution
        Generate pHp matrix
        '''
#         W = pipe_density(self.st['p'])
        # sampling density function

        try:
            if maxiter < self.last_iter:
            
                W = self.st['W']
            else: #maxiter > self.last_iter
                W = self.st['W']
                for pp in range(0,maxiter - self.last_iter):
 
    #             E = self.st['p'].dot(V1.dot(W))
                    E = self.forward(self.adjoint(W))
                    W = (W/E)             
                self.last_iter = maxiter   
        except:
       
                   
            W = numpy.ones((self.st['M'],),dtype=self.dtype)
    #         V1= self.st['p'].getH()
        #     VVH = V.dot(V.getH()) 
            
            for pp in range(0,maxiter):
    #             E = self.st['p'].dot(V1.dot(W))
 
                E = self.forward(self.adjoint(W))
                W = (W/E)

            self.last_iter = maxiter
        
        return W
        # density of the k-space, reduced size

    def _linear_phase(self, n_shift):
        """
        Private: Select the center of FOV
        """
        om = self.st['om']
        M = self.st['M']
        final_shifts = tuple(
            numpy.array(n_shift) +
            numpy.array(
                self.Nd) /
            2)
        phase = numpy.exp(
            1.0j *
            numpy.sum(
                om *
                numpy.tile(
                    final_shifts,
                    (M,
                     1)),
                1))
        # add-up all the linear phasees in all axes,

        self.st['p'] = scipy.sparse.diags(phase, 0).dot(self.st['p0'])
        return 0  # shifted sparse matrix
    def truncate_selfadjoint(self, tol):
        """
        Yet to be tested.
        """   
        indix=numpy.abs(self.st['pHp'].data)< tol
        self.st['pHp'].data[indix]=0

        self.st['pHp'].eliminate_zeros()

    def forward(self, x):
        """
        Forward NUFFT on CPU
        
        :param x: The input numpy array, with size=Nd
        :type: numpy array with dtype =numpy.complex64
        :return: gy: The output numpy array, with size=(M,)
        :rtype: numpy array with dtype =numpy.complex64
        """
        y = self.k2y(self.xx2k(self.x2xx(x)))

        return y

    def adjoint(self, y):
        """
        Adjoint NUFFT on CPU
        
        :param y: The input numpy array, with size=(M,)
        :type: numpy array with dtype =numpy.complex64
        :return: x: The output numpy array, with size=Nd
        :rtype: numpy array with dtype =numpy.complex64
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
#         x2 = self.k2xx(self.k2y2k(self.xx2k(x)))
        
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
        output_x = numpy.zeros(self.Kd, dtype=self.dtype,order='C')
#         output_x[crop_slice_ind(xx.shape)] = xx
        output_x.flat[self.KdCPUorder]=xx.flat[self.NdCPUorder]
        k = numpy.fft.fftn(output_x, self.Kd, range(0, self.ndims))

        return k
    def k2vec(self,k):
        
        k_vec = numpy.reshape(k, (numpy.prod(self.Kd), ), order='C')
   
        return k_vec
    
    def vec2y(self,k_vec):
        '''
        gridding: 
        
        '''
        y = self.sp.dot(k_vec)
        
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
        
        return k_vec
    def vec2k(self, k_vec):
        '''
        Sorting the vector to k-spectrum Kd array
        '''
        k = numpy.reshape(k_vec, self.Kd, order='C')
        
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
        
        k = numpy.fft.ifftn(k, self.Kd, range(0, self.ndims))
        xx= numpy.zeros(self.Nd,dtype=dtype, order='C')
        xx.flat[self.NdCPUorder]=k.flat[self.KdCPUorder]
#         xx = xx[crop_slice_ind(self.Nd)]
        return xx

    def xx2x(self, xx):
        """
        Private: rescaling, which is identical to the  _x2xx() method
        """
        x = self.x2xx(xx)
        return x
    def k2y2k(self, k):
        """
        Private: the integrated interpolation-gridding by the Sparse Matrix-Vector Multiplication
        """

        Xk = self.k2vec(k)
         
        k = self.spHsp.dot(Xk)
        k = self.vec2k(k)
        return k
    


# def test_installation():
#     '''
#     Test the installation
#     '''
#     import pkg_resources
#     PYNUFFT_PATH = pkg_resources.resource_filename('pynufft', './')
#     DATA_PATH = pkg_resources.resource_filename('pynufft', 'src/data/')
#     import os.path
#     
#     
#     print('Does pynufft.py exist? ',os.path.isfile(PYNUFFT_PATH+'pynufft.py'))
#     print('Does om1D.npz exist?',os.path.isfile(DATA_PATH+'om1D.npz'))
#     print('Does om2D.npz exist?',os.path.isfile(DATA_PATH+'om2D.npz'))
#     print('Does om3D.npz exist?',os.path.isfile(DATA_PATH+'om3D.npz'))
#     print('Does phantom_3D_128_128_128.npz exist?', os.path.isfile(DATA_PATH+'phantom_3D_128_128_128.npz'))
#     print('Does phantom_256_256.npz exist?', os.path.isfile(DATA_PATH+'phantom_256_256.npz'))
#     print('Does 1D_example.py exist?', os.path.isfile(PYNUFFT_PATH+'example/1D_example.py'))
#     print('Does 2D_example.py exist?', os.path.isfile(PYNUFFT_PATH+'example/1D_example.py'))
#     
# 
# def test_2D():
#     import pkg_resources
#     
#     DATA_PATH = pkg_resources.resource_filename('pynufft', 'src/data/')
# #     PHANTOM_FILE = pkg_resources.resource_filename('pynufft', 'data/phantom_256_256.txt')
#     import numpy
#     import matplotlib.pyplot
#     # load example image
# #     image = numpy.loadtxt(DATA_PATH +'phantom_256_256.txt')
#     image = scipy.misc.ascent()
#     
#     image = scipy.misc.imresize(image, (256,256))
#     
#     image=image.astype(numpy.float)/numpy.max(image[...])
#     #numpy.save('phantom_256_256',image)
#     matplotlib.pyplot.imshow(image, cmap=matplotlib.cm.gray)
#     matplotlib.pyplot.show()
#     print('loading image...')
# 
#     
#     
#     Nd = (256, 256)  # image size
#     print('setting image dimension Nd...', Nd)
#     Kd = (512, 512)  # k-space size
#     print('setting spectrum dimension Kd...', Kd)
#     Jd = (6, 6)  # interpolation size
#     print('setting interpolation size Jd...', Jd)
#     # load k-space points
#     # om = numpy.loadtxt(DATA_PATH+'om.txt')
#     om = numpy.load(DATA_PATH+'om2D.npz')['arr_0']
#     print('setting non-uniform coordinates...')
#     matplotlib.pyplot.plot(om[::10,0],om[::10,1],'o')
#     matplotlib.pyplot.title('non-uniform coordinates')
#     matplotlib.pyplot.xlabel('axis 0')
#     matplotlib.pyplot.ylabel('axis 1')
#     matplotlib.pyplot.show()
# 
#     NufftObj = NUFFT()
#     NufftObj.plan(om, Nd, Kd, Jd)
#     
#     y = NufftObj.forward(image)
#     print('setting non-uniform data')
#     print('y is an (M,) list',type(y), y.shape)
#     
# #     kspectrum = NufftObj.xx2k( NufftObj.solver(y,solver='bicgstab',maxiter = 100))
#     image_restore = NufftObj.solver(y, solver='cg',maxiter=10)
#     shifted_kspectrum = numpy.fft.fftshift( numpy.fft.fftn( numpy.fft.fftshift(image_restore)))
#     print('getting the k-space spectrum, shape =',shifted_kspectrum.shape)
#     print('Showing the shifted k-space spectrum')
#     
#     matplotlib.pyplot.imshow( shifted_kspectrum.real, cmap = matplotlib.cm.gray, norm=matplotlib.colors.Normalize(vmin=-100, vmax=100))
#     matplotlib.pyplot.title('shifted k-space spectrum')
#     matplotlib.pyplot.show()
#     image2 = NufftObj.solver(y, 'dc', maxiter = 25)
#     image3 = NufftObj.solver(y, 'L1TVLAD',maxiter=100, rho= 1)
#     image4 = NufftObj.solver(   y,'L1TVOLS',maxiter=100, rho= 1)
#     matplotlib.pyplot.subplot(1,3,1)
#     matplotlib.pyplot.imshow(image, cmap=matplotlib.cm.gray, norm=matplotlib.colors.Normalize(vmin=0.0, vmax=1))
#     matplotlib.pyplot.subplot(1,3,2)
#     matplotlib.pyplot.imshow(image3.real, cmap=matplotlib.cm.gray, norm=matplotlib.colors.Normalize(vmin=0.0, vmax=1))
#     matplotlib.pyplot.subplot(1,3,3)
#     matplotlib.pyplot.imshow(image4.real, cmap=matplotlib.cm.gray, norm=matplotlib.colors.Normalize(vmin=0.0, vmax=1))
#     matplotlib.pyplot.show()  
#   
# #     matplotlib.pyplot.imshow(image2.real, cmap=matplotlib.cm.gray, norm=matplotlib.colors.Normalize(vmin=0.0, vmax=1))
# #     matplotlib.pyplot.show()
#     maxiter =25
#     counter = 1
#     for solver in ('dc','bicg','bicgstab','cg', 'gmres','lgmres',  'lsmr', 'lsqr'):
#         if 'lsqr' == solver:
#             image2 = NufftObj.solver(y, solver,iter_lim=maxiter)
#         else:
#             image2 = NufftObj.solver(y, solver,maxiter=maxiter)
# #     image2 = NufftObj.solver(y, solver='bicgstab',maxiter=30)
#         matplotlib.pyplot.subplot(2,4,counter)
#         matplotlib.pyplot.imshow(image2.real, cmap=matplotlib.cm.gray, norm=matplotlib.colors.Normalize(vmin=0.0, vmax=1))
#         matplotlib.pyplot.title(solver)
#         print(counter, solver)
#         counter += 1
#     matplotlib.pyplot.show()
# 
# def test_asoperator():
#     
#     import pkg_resources
#     
#     DATA_PATH = pkg_resources.resource_filename('pynufft', 'src/data/')
# #     PHANTOM_FILE = pkg_resources.resource_filename('pynufft', 'data/phantom_256_256.txt')
#     import numpy
#     import matplotlib.pyplot
#     # load example image
# #     image = numpy.loadtxt(DATA_PATH +'phantom_256_256.txt')
#     image = scipy.misc.face(gray=True)
#     
#     image = scipy.misc.imresize(image, (256,256))
#     
#     image=image.astype(numpy.float)/numpy.max(image[...])
#     #numpy.save('phantom_256_256',image)
#     matplotlib.pyplot.imshow(image, cmap=matplotlib.cm.gray)
#     matplotlib.pyplot.show()
#     print('loading image...')
# 
#     
#     
#     Nd = (256, 256)  # image size
#     print('setting image dimension Nd...', Nd)
#     Kd = (512, 512)  # k-space size
#     print('setting spectrum dimension Kd...', Kd)
#     Jd = (6, 6)  # interpolation size
#     print('setting interpolation size Jd...', Jd)
#     # load k-space points
#     # om = numpy.loadtxt(DATA_PATH+'om.txt')
#     om = numpy.load(DATA_PATH+'om2D.npz')['arr_0']
#     print('setting non-uniform coordinates...')
#     matplotlib.pyplot.plot(om[::10,0],om[::10,1],'o')
#     matplotlib.pyplot.title('non-uniform coordinates')
#     matplotlib.pyplot.xlabel('axis 0')
#     matplotlib.pyplot.ylabel('axis 1')
#     matplotlib.pyplot.show()
# 
#     NufftObj = NUFFT()
#     NufftObj.plan(om, Nd, Kd, Jd)
#         
#     print('NufftObj.dtype=',NufftObj.dtype, '  NufftObj.shape=',NufftObj.shape)
#     
#     y1 = NufftObj.forward(image)
#     x_vec= numpy.reshape(image,  (numpy.prod(NufftObj.st['Nd']), ) , order='F')
#     
#     y2 = NufftObj._matvec(x_vec)
#     
#     A = scipy.sparse.linalg.LinearOperator(NufftObj.shape, matvec=NufftObj._matvec, rmatvec=NufftObj._adjoint, dtype=NufftObj.dtype)
# #     scipy.sparse.linalg.aslinearoperator(A)
#     
#     print(type(A))
# #     y1 = A.matvec(x_vec)
#     print('y1.shape',numpy.shape(y1))  
#     import time
#     t0=time.time()
#     KKK = scipy.sparse.linalg.lsqr(A, y1, )
#     print(numpy.shape(KKK))  
#     
#     
#     print(time.time() - t0)
#     
#     x2 = numpy.reshape(KKK[0], NufftObj.st['Nd'], order='F')
#     
#     
#     matplotlib.pyplot.subplot(2,1,1)
#     matplotlib.pyplot.imshow(x2.real,cmap=matplotlib.cm.gray)
#     matplotlib.pyplot.subplot(2,1,2)
#     matplotlib.pyplot.imshow(image,cmap=matplotlib.cm.gray)
#     
#     matplotlib.pyplot.show()
#     
#     
#     print('y1 y2 close? ', numpy.allclose(y1, y2))
# def test_multidimension():
#     for ndims in range(1, 6):
#         Nd= ()
#         Kd=()
#         Jd=()
#         om = numpy.random.randn(2,ndims)
#         for pp in range(0, ndims):
#             Nd += (128,)
#             Kd += (256,)
#             Jd += (4,)
# #         Nd =tuple([slice(0, 16) for ss in range(0, ndims)])  # image size
# #         print('setting image dimension Nd...', Nd)
# #         Kd = tuple([slice(0, 32) for ss in range(0, ndims)])  # k-space size
# #         print('setting spectrum dimension Kd...', Kd)
# #         Jd = tuple([slice(0, 6) for ss in range(0, ndims)])   # interpolation size
# #         print('setting interpolation size Jd...', Jd)
#         NufftObj = NUFFT()
#         NufftObj.plan(om, Nd, Kd, Jd)
#         print(ndims,'-dimensional NUFFT created!')
#     y = NufftObj.forward(image) 

# if __name__ == '__main__':
#     """
#     Test the module pynufft
#     """
#     test_2D()
#     test_multidimension()
#     test_asoperator()
#     test_installation()
