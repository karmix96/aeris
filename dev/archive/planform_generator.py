""" 
Planform_2nd_Approach_V5: 
Is the V4 with dihedral and twist consideration.
We set combination of dihedral and twist in every group begining and end point. In between, we interpolate.
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import CubicSpline
import aerosandbox as asb
import aerosandbox.numpy as np

# Number of iterations and control points for the LE curve
n_iter = 10  # For demonstration, just run one iteration
n_points = 10  # total control points along the LE
Nspl_1 = 50
Nspl_2 = 50

# Define a new function that blends the cubic spline with a linear baseline.
def generate_spline_linear(y_vals, x_vals, split_index, curvature_strength=0.7):
    # Create a fine grid over the first segment (spline part)
    y_spline = np.linspace(np.min(y_vals), y_vals[split_index], Nspl_1)
    
    # Get the full cubic spline result.
    spline_func = CubicSpline(y_vals, x_vals, bc_type='clamped')
    x_spline_full = spline_func(y_spline)
    
    # Create a linear baseline between the endpoints.
    x_linear_baseline = np.interp(y_spline, [np.min(y_vals), y_vals[split_index]], [x_vals[0], x_vals[split_index]])
    
    # Blend between the linear and spline curves.
    # curvature_strength=1.0 gives the full cubic spline,
    # 0 gives a straight line, >1 exaggerates the curvature.
    x_spline = x_linear_baseline + curvature_strength * (x_spline_full - x_linear_baseline)
    
    # Second part: linear interpolation.
    y_linear = np.linspace(y_vals[split_index], y_vals[-1], Nspl_2)
    x_linear = np.interp(y_linear, [y_vals[split_index], y_vals[-1]],
                         [x_vals[split_index], x_vals[-1]])
    
    return np.concatenate((y_spline, y_linear[1:])), np.concatenate((x_spline, x_linear[1:]))

# Example: Set a desired curvature strength parameter.
desired_curvature_strength = 0.3 # Change this value to control the curvature

c1_min, c1_max = 1.2, 2
c2_min_ratio, c2_max_ratio = 0.45, 0.65
c3_min_ratio, c3_max_ratio = 0.30, 0.45
c4_min_ratio, c4_max_ratio = 0.07, 0.2

b_total_min, b_total_max = 1.2, 2 
c1_btot_ratio_min, c1_btot_ratio_max = c1_min/b_total_max, c1_max/b_total_min

b3_min_lim = 0.45
b3_max_lim = 0.55

split_ratio_min = 0.35
split_ratio_max = 0.55

min_AoA = -1
max_AoA = 5

sw1_min, sw1_max = 25, 60
sw2_min, sw2_max = 10, 60
sw3_min, sw3_max = 0, 40

c1 = np.random.uniform(c1_min, c1_max)
c2 = c1*np.random.uniform(c2_min_ratio, c2_max_ratio)
c3 = c1*np.random.uniform(c3_min_ratio, c3_max_ratio)
c4 = c1*np.random.uniform(c4_min_ratio, c4_max_ratio)

b_total = c1/np.random.uniform(c1_btot_ratio_min, c1_btot_ratio_max)
b3 = b_total * np.random.uniform(b3_min_lim, b3_max_lim )

remaining_b = b_total - b3
split_ratio = np.random.uniform(split_ratio_min, split_ratio_max)  # Split b1 and b2

b1 = remaining_b * split_ratio
b2 = remaining_b - b1

sw1 = -np.random.uniform(sw1_min, sw1_max)
sw2 = -np.random.uniform(sw2_min, sw2_max)
sw3 = -np.random.uniform(sw3_min, sw3_max)
sw1_rad, sw2_rad, sw3_rad = np.radians(90 - np.array([sw1, sw2, sw3]))

# Divide the LE curve into three groups based on the ratios of the LE segments:
N1 = int(round((b1 / b_total) * (n_points - 1)))  # points in group 1
N2 = int(round((b2 / b_total) * (n_points - 1)))  # points in group 2
N3 = (n_points - 1) - N1 - N2                     # remainder (group 3)

# Function to generate group segments with slight variation.
def generate_group_segments(N, total_length, variation=0.25):
    mean_seg = total_length / N
    segments = np.random.uniform(1 - variation, 1 + variation, N) * mean_seg
    segments = segments * (total_length / np.sum(segments))
    return segments

# Generate LE segment lengths groupwise:
b_group1 = generate_group_segments(N1, b1)
b_group2 = generate_group_segments(N2, b2)
b_group3 = generate_group_segments(N3, b3)
b_le = np.concatenate((b_group1, b_group2, b_group3))

# Function to generate sweep angles with slight variation.
def generate_group_sweep(N, fixed_s, variation=0.1):
    return fixed_s * np.random.uniform(1 - variation, 1 + variation, N)

s_group1 = generate_group_sweep(N1, sw1_rad)
s_group2 = generate_group_sweep(N2, sw2_rad)
s_group3 = generate_group_sweep(N3, sw3_rad)
s_rad_le = np.concatenate((s_group1, s_group2, s_group3))

# Function to compute the LE control points.
def compute_le_curve(x0, y0, b_params, s_rad_params):
    x_points = [x0]
    y_points = [y0]
    for b, s_rad in zip(b_params, s_rad_params):
        dx = b / np.tan(s_rad)
        x_points.append(x_points[-1] - dx)  # moving left
        y_points.append(y_points[-1] + b)
    return np.array(x_points), np.array(y_points)

# Define the LE root
x0_le, y0_le = 0.0, 0.0
x_le, y_le = compute_le_curve(x0_le, y0_le, b_le, s_rad_le)

# Generate the chord (TE) distribution.
key_indices = [0, N1, N1 + N2, n_points - 1]
key_chords = np.array([c1, c2, c3, c4])
all_indices = np.arange(n_points)
chords = np.interp(all_indices, key_indices, key_chords)

# Define TE control points by shifting the LE points by the chord lengths.
x_te = x_le + chords
y_te = y_le.copy()  # same spanwise positions

# Choose a split index for spline-linear transition.
split_idx = int(n_points * 0.55)
front_y_fine, front_x_fine = generate_spline_linear(
    y_le, x_le, split_idx, curvature_strength=desired_curvature_strength
)
rear_y_fine, rear_x_fine   = generate_spline_linear(
    y_te, x_te, split_idx, curvature_strength=desired_curvature_strength
)

# Mirror the upper half to create the lower surface.
front_x_mirrored, front_y_mirrored = front_x_fine, -front_y_fine
rear_x_mirrored, rear_y_mirrored   = rear_x_fine, -rear_y_fine

# --- Plot the design for this iteration ---
plt.figure(figsize=(10,6))

# Plot LE and TE control points.
plt.plot(x_le, y_le, 'b-o', markersize=2, label="LE Control Points")
plt.plot(x_te, y_te, 'r-o', markersize=2, label="TE Control Points")

# Plot chord projection lines.
for i in range(n_points):
    plt.plot([x_le[i], x_te[i]], [y_le[i], y_le[i]], 'k--', alpha=0.3)

# Plot the smooth spline + linear curves (upper surface).
plt.plot(front_x_fine, front_y_fine, 'g-', linewidth=2, label="Front Spline+Linear")
plt.plot(rear_x_fine, rear_y_fine, 'm-', linewidth=2, label="Rear Spline+Linear")

# Plot the mirrored lower surfaces.
plt.plot(front_x_mirrored, front_y_mirrored, 'g--', linewidth=2, label="Front Lower Surface")
plt.plot(rear_x_mirrored, rear_y_mirrored, 'm--', linewidth=2, label="Rear Lower Surface")

plt.xlabel("x (chordwise)")
plt.ylabel("y (spanwise)")
plt.grid(True)
plt.legend(loc="best", fontsize=8)
plt.axis("equal")
plt.tight_layout()
# plt.show()

# Create the airplane using aerosandbox.
airfoil = asb.Airfoil("naca4412")

# --- NEW: Define twist and dihedral arrays for each cross-section using random boundary values for each group ---
num_sections = Nspl_1 + Nspl_2 - 1

# Determine the group boundaries from the original LE control points.
# These boundaries correspond to the start, group1 end, group2 end, and the overall end.
group_boundary_y = np.array([y_le[0], y_le[N1], y_le[N1 + N2], y_le[-1]])

# Generate random twist values at these boundaries (for example, between -2° and 0°).
twist_boundaries = np.random.uniform(-5, 5, size=4)

# For dihedral, set the first boundary to 0, and generate the remaining three randomly between 0 and 5°.
dihedral_boundaries = np.concatenate(([0], np.random.uniform(-5, 5, size=3)))

# Interpolate these boundary values along the span based on the fine discretization's y-coordinate.
twist_array = np.interp(front_y_fine, group_boundary_y, twist_boundaries)
dihedral_array = np.interp(front_y_fine, group_boundary_y, dihedral_boundaries)

# Interpolate these boundary values along the span based on the fine discretization's y-coordinate.
twist_array = np.interp(front_y_fine, group_boundary_y, twist_boundaries)
dihedral_array = np.interp(front_y_fine, group_boundary_y, dihedral_boundaries)

wing_xsecs = [
asb.WingXSec(
    xyz_le=[
        front_x_fine[i],
        front_y_fine[i],
        front_y_fine[i] * np.tan(np.radians(dihedral_array[i]))
    ],
    chord=rear_x_fine[i] - front_x_fine[i],
    twist=twist_array[i],
    airfoil=airfoil
)
for i in range(num_sections)
]

bwb = asb.Airplane(
    name="BWB_Airplane",
    xyz_ref=[0, 0, 0],
    wings=[
        asb.Wing(
            name="BWB",
            symmetric=True,
            xsecs=wing_xsecs
        )
    ]
)
bwb.draw()

bwb_wing=asb.Wing(
    xsecs=wing_xsecs
)
print(f"bwb_aspect_ratio = {bwb_wing.aspect_ratio()}")

