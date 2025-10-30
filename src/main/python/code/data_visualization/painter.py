
from matplotlib import pyplot as plot
import os
import sys
from scripts.charts.work_hour_number_of_friends import plot_1, plot_2, plot_3, plot_4, plot_5, plot_6, plot_7, plot_8, plot_9, plot_10, plot_11, plot_12, plot_13, plot_14, plot_15, plot_16


def plot_all(data, text_on_plot, output_dir="./results/plots", show=False, preprocess_type="default"):
    print("plot_1: plot_all")

    error_counter = 0
    error_counter += draw_plot(plot_1, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_2, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_3, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_4, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_5, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_6, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_7, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_8, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_9, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_10, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_11, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_12, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_13, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_14, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_15, data,
                               text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_16, data,
                               text_on_plot, output_dir, show, preprocess_type)

    if error_counter > 0:
        print(f"Error counter: {error_counter}")
    else:
        print("All plots are successfully created.")


def plot_min(data, text_on_plot, output_dir="./results/plots", show=False, preprocess_type="default"):
    print("plot_1: plot_min")

    error_counter = 0
    error_counter += draw_plot(plot_1, data, text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_3, data, text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_5, data, text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_8, data, text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_10, data, text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_12, data, text_on_plot, output_dir, show, preprocess_type)
    error_counter += draw_plot(plot_14, data, text_on_plot, output_dir, show, preprocess_type)

    if error_counter > 0:
        print(f"Error counter: {error_counter}")
    else:
        print("All plots are successfully created.")


def draw_plot(func, data, text_on_plot, output_dir, show=False, preprocess_type="default"):
    if preprocess_type != "default":
        output_dir = output_dir + "/" + preprocess_type
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    data = preprocess(data, preprocess_type, text_on_plot, output_dir)
    if preprocess_type != "default":
        text_on_plot = text_on_plot + "_" + preprocess_type

    try:
        func(data, text_on_plot, output_dir, show)
        plot.close()
        return 0
    except:
        print(f"Error: draw_plot")
        print(f"Error: function: {func.__name__}")
        print(f"Error: data:\n {data.shape}")
        print(f"Error: data:\n {data.head()}")
        print(f"Error: text_on_plot: {text_on_plot}")
        print(f"Error: output_dir: {output_dir}")
        print(f"Error: show: {show}")
        print(f"Error: preprocess_type: {preprocess_type}")
        print(f"Error message: {sys.exc_info()[0]}")
        print(f"Error message: {sys.exc_info()[1]}")
        print(f"Error message: {sys.exc_info()[2]}")
        print(f"Error message: {sys.exc_info()[3]}")
        plot.close()

        return 1


def preprocess(data, preprocess_type, text_on_plot, output_dir="./results/plots"):
    import numpy
    if os.path.exists(output_dir) == False:
        os.makedirs(output_dir)

    if "default" in preprocess_type:
        preprocess_type = "meanfloor"
    data.to_csv(f"{output_dir}/unprocessed.csv", index=False)
    if "mean" in preprocess_type:
        print(f"preprocess: mean for {text_on_plot}")
        data = data.groupby('agentId').mean().reset_index()
        data.to_csv(f"{output_dir}/mean.csv", index=False)
    if "floor" in preprocess_type:
        print(f"preprocess: floor for {text_on_plot}")
        w_index = data.columns.get_loc('workHours')
        data.iloc[:, w_index] = data.iloc[:, w_index].apply(numpy.floor)
        data.to_csv(f"{output_dir}/floor_workHours.csv", index=False)
    if "round" in preprocess_type:
        print(f"preprocess: round for {text_on_plot}")
        w_index = data.columns.get_loc('workHours')
        data.iloc[:, w_index] = data.iloc[:, w_index].apply(numpy.round)
        data.to_csv(f"{output_dir}/round_workHours.csv", index=False)
    if "ceil" in preprocess_type:
        print(f"preprocess: ceil for {text_on_plot}")
        w_index = data.columns.get_loc('workHours')
        data.iloc[:, w_index] = data.iloc[:, w_index].apply(numpy.ceil)
        data.to_csv(f"{output_dir}/ceil_workHours.csv", index=False)

    

    return data
