"""
Chart Utilities for Data2Dashboard
=================================

This module provides utility functions to standardize and enhance charts produced
by the Data2Dashboard system. It includes functions to fix common legend issues,
standardize colors, and ensure consistent styling across visualizations.
"""

import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from pathlib import Path



def fix_legends(fig=None, ax=None, title=None, loc='best', fontsize=10):
    """Improve legend appearance and placement.
    
    Args:
        fig: matplotlib Figure object (optional)
        ax: matplotlib Axes object (optional)
        title: Legend title (optional)
        loc: Legend location (default: 'best')
        fontsize: Font size for legend text (default: 10)
    """
    if fig is None and ax is None:
        ax = plt.gca()
    
    target_ax = ax if ax is not None else plt.gca()
    
    # Get existing legend if any
    legend = target_ax.get_legend()
    
    if legend is not None:
        # Get handles and labels
        handles, labels = target_ax.get_legend_handles_labels()
        
        # If we have handles but no labels, try to generate meaningful labels
        if len(handles) > 0 and (len(labels) == 0 or all(not label for label in labels)):
            labels = [f"Series {i+1}" for i in range(len(handles))]
        
        # Recreate legend with improved settings
        target_ax.legend(
            handles=handles,
            labels=labels,
            title=title or legend.get_title().get_text(),
            loc=loc,
            fontsize=fontsize,
            framealpha=0.7,
            edgecolor='lightgray'
        )
    
    return target_ax

def create_color_palette(n_colors, palette_name='viridis'):
    """Create a colorblind-friendly color palette.
    
    Args:
        n_colors: Number of colors needed
        palette_name: Name of the colormap to use (default: 'viridis')
                     Options: 'viridis', 'plasma', 'cividis', 'Paired'
    
    Returns:
        List of color values
    """
    if palette_name == 'Paired':
        cmap = plt.get_cmap('Paired')
    else:
        cmap = getattr(plt.cm, palette_name, plt.get_cmap('viridis'))
    
    return [cmap(i) for i in np.linspace(0, 0.9, n_colors)]

def enhance_plot(fig=None, ax=None, title=None, xlabel=None, ylabel=None, 
                legend_title=None, legend_loc='best', grid=True):
    """Apply consistent styling to a plot.
    
    Args:
        fig: matplotlib Figure object (optional)
        ax: matplotlib Axes object (optional)
        title: Plot title (optional)
        xlabel: X-axis label (optional)
        ylabel: Y-axis label (optional)
        legend_title: Title for the legend (optional)
        legend_loc: Location for the legend (default: 'best')
        grid: Whether to show grid lines (default: True)
    """
    if fig is None and ax is None:
        ax = plt.gca()
    
    target_ax = ax if ax is not None else plt.gca()
    
    if title:
        target_ax.set_title(title, fontsize=14, pad=10)
    
    if xlabel:
        target_ax.set_xlabel(xlabel, fontsize=12, labelpad=8)
    
    if ylabel:
        target_ax.set_ylabel(ylabel, fontsize=12, labelpad=8)
    
    # Improve tick labels
    target_ax.tick_params(axis='both', labelsize=10)
    
    # Add grid if requested
    if grid:
        target_ax.grid(alpha=0.3, linestyle='--')
    
    # Fix legend
    fix_legends(ax=target_ax, title=legend_title, loc=legend_loc)
    
    return target_ax

def fix_pie_chart(ax=None, title=None, startangle=90, with_labels=True,
                 autopct='%1.1f%%', explode=None, colors=None):
    """Standardize pie chart appearance.
    
    Args:
        ax: matplotlib Axes object (optional)
        title: Chart title (optional)
        startangle: Starting angle for the pie chart (default: 90)
        with_labels: Whether to show labels (default: True)
        autopct: Format for percentage display (default: '%1.1f%%')
        explode: Explode values for pie segments (optional)
        colors: Custom colors for pie segments (optional)
    """
    if ax is None:
        ax = plt.gca()
    
    # Ensure pie is circular
    ax.set_aspect('equal')
    
    if title:
        ax.set_title(title, fontsize=14, pad=10)
    
    # Get the wedges (patches) from the current pie chart
    wedges = [child for child in ax.get_children() if isinstance(child, patches.Wedge)]
    
    # Update wedge properties if there are wedges
    if wedges and colors:
        for i, wedge in enumerate(wedges):
            if i < len(colors):
                wedge.set_facecolor(colors[i])
                wedge.set_edgecolor('white')
                wedge.set_linewidth(1)
    
    return ax

def fix_multiple_series(data, kind='bar', stacked=False, figsize=(10, 6), 
                       colormap='viridis', title=None, xlabel=None, ylabel=None,
                       legend_title=None, legend_loc='best'):
    """Create a properly formatted multi-series chart.
    
    Args:
        data: DataFrame containing the data to plot
        kind: Type of plot ('bar', 'line', etc.) (default: 'bar')
        stacked: Whether to stack the series (default: False)
        figsize: Figure size as (width, height) (default: (10, 6))
        colormap: Colormap to use (default: 'viridis')
        title: Plot title (optional)
        xlabel: X-axis label (optional)
        ylabel: Y-axis label (optional)
        legend_title: Title for the legend (optional)
        legend_loc: Location for the legend (default: 'best')
    
    Returns:
        matplotlib Figure and Axes objects
    """
    fig, ax = plt.subplots(figsize=figsize)
    
    data.plot(
        kind=kind,
        stacked=stacked,
        ax=ax,
        colormap=colormap,
        width=0.7 if kind == 'bar' else None,
        edgecolor='white' if kind == 'bar' else None,
        linewidth=3 if kind == 'line' else None,
        alpha=0.8
    )
    
    enhance_plot(
        ax=ax,
        title=title,
        xlabel=xlabel,
        ylabel=ylabel,
        legend_title=legend_title,
        legend_loc=legend_loc
    )
    
    fig.tight_layout()
    return fig, ax

def post_process_all_figures(directory='figures'):
    """Post-process all PNG figures in the specified directory.
    
    Args:
        directory: Path to the directory containing figures (default: 'figures')
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        print(f"Directory {directory} not found.")
        return
    
    for fig_path in dir_path.glob('*.png'):
        try:
            # Load the figure
            fig = plt.figure()
            img = plt.imread(fig_path)
            plt.imshow(img)
            
            # Apply standard styling
            ax = plt.gca()
            ax.axis('off')  # Hide axes for the image
            
            # Save the enhanced figure
            plt.tight_layout()
            plt.savefig(fig_path, dpi=300, bbox_inches='tight')
            plt.close(fig)
            
            print(f"Post-processed: {fig_path.name}")
        except Exception as e:
            print(f"Error processing {fig_path.name}: {e}")
    
    print(f"Completed post-processing of figures in {directory}") 
