"""Top-level class for Calibration"""
import numpy as np
import cv2 as cv
import gc
import pyquaternion as pyquat
from scipy.stats import multivariate_normal
from scipy.linalg import expm

from calibration.utils.data_utils import *
from calibration.utils.pc_utils import *

import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm
from matplotlib.ticker import MaxNLocator
from scipy.ndimage.filters import gaussian_filter, convolve

from calibration.pc_edge_detector import PcEdgeDetector
from calibration.img_edge_detector import ImgEdgeDetector


class CameraLidarCalibrator:

    def __init__(self, cfg, visualize=False):
        self.pc_detector = PcEdgeDetector(cfg, visualize=visualize)
        gc.collect()
        self.img_detector = ImgEdgeDetector(cfg, visualize=visualize)
        gc.collect()
        self.pixels = None
        self.pixels_mask = None
        self.K = cfg.K
        self.R, self.T = load_lid_cal(cfg.calib_dir)
        self.tau = cfg.tau_init

        self.visualize = visualize
        # TODO: Change the methods below to use the new variables in pc_detector and img_detector

    @staticmethod
    def transform_to_tau(R, T):
        tau = np.zeros(6)
        quat = pyquat.Quaternion(matrix=R)
        tau[:3] = quat.angle * quat.axis
        tau[3:] = np.squeeze(T)

        return tau

    def pc_to_pixels(self):
        '''
        Generate pixel coordinate for all points
        '''
        one_mat = np.ones((self.pc_detector.pcs.shape[0], 1))
        point_cloud = np.concatenate((self.pc_detector.pcs, one_mat), axis=1)

        # TODO: Perform transform without homogeneous term,
        #       if too memory intensive

        # Project point into Camera Frame
        point_cloud_cam = np.matmul(np.hstack((self.R, self.T)), point_cloud.T)

        # Remove the Homogeneous Term
        point_cloud_cam = np.matmul(self.K, point_cloud_cam)

        # Normalize the Points into Camera Frame
        self.pixels = point_cloud_cam[::] / point_cloud_cam[::][-1]
        self.pixels = np.delete(self.pixels, 2, axis=0)
        self.pixels = self.pixels.T

        # Remove pixels that are outside image
        inside_mask_x = np.logical_and((self.pixels[:, 0] >= 0),
                                       (self.pixels[:, 0] <= self.img_detector.img_w))
        inside_mask_y = np.logical_and((self.pixels[:, 1] >= 0),
                                       (self.pixels[:, 1] <= self.img_detector.img_h))
        inside_mask = np.logical_and(inside_mask_x, inside_mask_y)

        if self.visualize:
            blank = np.zeros((self.img_detector.img_h, self.img_detector.img_w))
            blank[self.pixels[inside_mask, 1].astype(np.int), self.pixels[inside_mask, 0].astype(np.int)] = 255
            cv.imshow('Projected Lidar Edges', blank)
            cv.waitKey(0)

        self.pixels_mask = inside_mask

    def draw_points(self, image=None, FULL=True):
        """
        Draw points within corresponding camera's FoV on image provided.
        If no image provided, points are drawn on an empty(black) background.
        """

        if image is not None:
            image = np.dstack((image, image, image))
            hsv_image = cv.cvtColor(image, cv.COLOR_BGR2HSV)
        else:
            hsv_image = np.zeros(self.img.shape).astype(np.uint8)

        color = self.pc_to_colors()
        if FULL:
            index = range(self.pixels.shape[1])
        else:
            index = np.random.choice(self.pixels.shape[1],
                                     size=int(self.pixels.shape[1] / 10),
                                     replace=False)
        for i in index:
            if self.points[i, 0] < 0:
                continue
            if ((self.pixels[0, i] < 0) | (self.pixels[1, i] < 0) |
                (self.pixels[0, i] > hsv_image.shape[1]) |
                    (self.pixels[1, i] > hsv_image.shape[0])):
                continue
            cv.circle(
                hsv_image,
                (np.int32(self.pixels[0, i]), np.int32(self.pixels[1, i])), 1,
                (int(color[i]), 255, 255), -1)

        return cv.cvtColor(hsv_image, cv.COLOR_HSV2BGR)

    def pc_to_colors(self, min_d=0, max_d=120):
        """
        print Color(HSV's H value) corresponding to distance(m)
        close distance = red , far distance = blue
        """
        dist = np.sqrt(
            np.add(np.power(self.points[:, 0],
                            2), np.power(self.points[:, 1], 2),
                   np.power(self.points[:, 2], 2)))
        np.clip(dist, 0, max_d, out=dist)
        # max distance is 120m but usually not usual
        return (((dist - min_d) / (max_d - min_d)) * 120).astype(np.uint8)

    def compute_cost(self, sigma_in):
        """Compute cost for the current tau (extrinsics)"""

        # Project lidar points
        self.pc_to_pixels()

        # GMM Cost
        cost = 0
        # iterate over lidar edge points
        for idx in range(self.pc_detector.pcs_edge_idxs.shape[0]):
            pt_idx = self.pc_detector.pcs_edge_idxs[idx]

            # check if pixel lands within image bounds
            if self.pixels_mask[pt_idx]:

                # lidar edge weight
                w_i = self.pc_detector.pcs_edge_scores[pt_idx]

                # gaussian parameters
                mu = self.pixels[pt_idx, :]
                sigma = sigma_in/np.linalg.norm(self.pc_detector.pcs[pt_idx, :])
                cov_mat = np.diag([sigma, sigma])

                # neighborhood params
                min_x = max(0, int(mu[0] - 3*sigma))
                max_x = min(self.img_detector.img_w, int(mu[0] + 3*sigma))
                min_y = max(0, int(mu[1] - 3*sigma))
                max_y = min(self.img_detector.img_h, int(mu[1] + 3*sigma))
                num_ed_pixels = np.sum(self.img_detector.imgs_edges[min_y: max_y, min_x: max_x])

                # iterate over 3-sigma neighborhood
                for x in range(min_x, max_x):
                    for y in range(min_y, max_y):

                        # check if current img pixel is an edge pixel
                        if self.img_detector.imgs_edges[y, x]:
                            w_j = self.img_detector.imgs_edge_scores[y, x]
                            w_ij = 0.5*(w_i + w_j)/num_ed_pixels
                            cost += w_ij*multivariate_normal.pdf([x, y], mu, cov_mat)

        return cost

    def compute_gradient(self, sigma_in):

        # GMM Cost
        gradient = np.zeros(6)

        omega = self.tau[:3]
        jac = jacobian(omega)

        # TODO: Simplify
        angle = np.linalg.norm(omega, 2)
        axis = omega/angle
        quat = pyquat.Quaternion(axis=axis, radians=angle)
        R = quat.rotation_matrix

        # TODO: Simplify
        f_x = self.K[0, 0]
        f_y = self.K[1, 1]
        c_x = self.K[0, 2]
        c_y = self.K[1, 2]

        # iterate over lidar edge points
        for idx in range(self.pc_detector.pcs_edge_idxs.shape[0]):
            pt_idx = self.pc_detector.pcs_edge_idxs[idx]

            # check if pixel lands within image bounds
            if self.pixels_mask[pt_idx]:

                # lidar edge weight
                w_i = self.pc_detector.pcs_edge_scores[pt_idx]

                # gaussian parameters
                mu = self.pixels[pt_idx, :]
                sigma = sigma_in / np.linalg.norm(self.pc_detector.pcs[pt_idx, :])
                cov_mat = np.diag([sigma, sigma])

                # neighborhood params
                min_x = max(0, int(mu[0] - 3 * sigma))
                max_x = min(self.img_detector.img_w, int(mu[0] + 3 * sigma))
                min_y = max(0, int(mu[1] - 3 * sigma))
                max_y = min(self.img_detector.img_h, int(mu[1] + 3 * sigma))
                num_ed_pixels = np.sum(self.img_detector.imgs_edges[min_y: max_y, min_x: max_x])

                # iterate over 3-sigma neighborhood
                for x in range(min_x, max_x):
                    for y in range(min_y, max_y):

                        # check if current img pixel is an edge pixel
                        if self.img_detector.imgs_edges[y, x]:
                            w_j = self.img_detector.imgs_edge_scores[y, x]
                            w_ij = 0.5 * (w_i + w_j) / num_ed_pixels

                            M = -np.dot(skew(R*self.pc_detector.pcs[pt_idx]), jac)
                            dxc_dtau = np.append(M[0, :], [1, 0, 0])
                            dyc_dtau = np.append(M[1, :], [0, 1, 0])
                            dzc_dtau = np.append(M[2, :], [0, 0, 1])


                            # TODO: Gaussian derivative
                            dG_du = 1
                            dG_dv = 1

                            x_c, y_c, z_c = self.pc_detector.pcs[pt_idx]
                            du_dxc = f_x/z_c
                            du_dyc = 0
                            du_dzc = -(f_x*x_c)/(z_c**2)
                            dv_dxc = 0
                            dv_dyc = f_y / z_c
                            dv_dzc = -(f_y*y_c)/(z_c**2)

                            du_dtau = (du_dxc * dxc_dtau) + (du_dyc * dyc_dtau) + (du_dzc * dzc_dtau)
                            dv_dtau = (dv_dxc * dxc_dtau) + (dv_dyc * dyc_dtau) + (dv_dzc * dzc_dtau)

                            gradient += (dG_du*du_dtau) + (dG_dv*dv_dtau)

        return gradient

