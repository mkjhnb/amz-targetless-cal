import argparse
import json


def command_line_parser():
    parser = argparse.ArgumentParser(
        add_help=True,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # For PcEdgeDetector
    parser.add_argument(
        '--pc_dir', type=str, default='',
        help='Path to directory containing the point cloud files')

    parser.add_argument(
        '--pc_subsample', type=float, default=1.0,
        help='Subsampling fraction for the pointcloud to reduce computation while debugging')

    parser.add_argument(
        '--pc_ed_rad_nn', type=float, default=0.1,
        help='Radius in which to include neighbors during point cloud edge detection')

    parser.add_argument(
        '--pc_ed_num_nn', type=float, default=75,
        help='Min number of nearest neighbors used')

    parser.add_argument(
        '--pc_ed_score_thr', type=float, default=0.35,
        help='Threshold above which points are considered edge points')

    parser.add_argument(
        '--pc_ed_method', type=str, default='sed',
        help='Method used for image edge detection: sed or canny')

    parser.add_argument(
        '--im_ed_score_thr', type=float, default=0.25,
        help='Threshold used for SED')

    parser.add_argument(
        '--im_ed_score_thr1', type=float, default=200,
        help='Lower threshold for Canny')

    parser.add_argument(
        '--im_ed_score_thr2', type=float, default=300,
        help='Upper threshold for Canny')

    parser.add_argument(
        '--img_dir', type=str, default='',
        help='Path to directory containing the image files')

    # For CameraLidarCalibrator
    parser.add_argument(
        '--calib_dir', type=str, default='',
        help='Initial guess of the transformation')

    parser.add_argument(
        '--frames', type=json.loads, default='[1, 6, 19]',
        help='Initial guess of the transformation')

    parser.add_argument(
        '--tau_init', type=json.loads, default='[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]',
        help='Initial guess of the transformation')

    parser.add_argument(
        '--K',
        type=json.loads,
        default='[[7.215377e+02, 0.000000e+00, 6.095593e+02], \
                  [0.000000e+00, 7.215377e+02, 1.728540e+02], \
                  [0.000000e+00, 0.000000e+00, 1.000000e+00]]',
        help='3x3 camera matrix')

    parser.add_argument(
        '--sig_in', type=json.loads, default='[3.0 ,2.0 ,1.0]',
        help='Values for the refinement steps')

    cfg = parser.parse_args()

    return cfg
