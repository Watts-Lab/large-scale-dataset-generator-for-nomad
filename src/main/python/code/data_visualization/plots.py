import pandas
import numpy
import matplotlib.pyplot as plot
import seaborn


def plot_0(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_0: ")
    print(f"plot_0: text_on_plot: {text_on_plot}")
    print(f"plot_0: output_dir: {output_dir}")
    print(f"plot_0: show: {show}")
    print(f"plot_0: data: {data.shape}")
    print(f"plot_0: data: {data.head()}")
    print(f"plot_0: data: {data.describe()}")
    print(f"plot_0: data: {data.info()}")
    print(f"plot_0: data: {data.dtypes}")
    print(f"plot_0: data: {data.columns}")

    # draw a simple scatter plot
    plot.figure(figsize=(10, 6))
    seaborn.set_theme(style="whitegrid")
    seaborn.set_context("paper", font_scale=0.8)
    seaborn.set_palette("pastel")
    seaborn.scatterplot(data=data, x='numberOfFriends',  y='workHours')
    plot.title("numberOfFriends vs Work Hours")
    plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/scatter_plot.png")
    if show == True:
        plot.show()
        plot.close()
    else:
        plot.close()


def plot_1(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_1: plot_histogram")

    bins_friends = [f for f in range(0, 400, 10)]
    bins_work_hours = [3, 4, 5, 6, 7, 8, 9, 10, 11]
    bins_joviality = numpy.arange(0, 1.1, 0.1)

    plot.figure(figsize=(10, 6))
    plot.subplot(1, 3, 1)
    seaborn.histplot(data=data, x='numberOfFriends', kde=True,
                     color='blue', bins=bins_friends)
    plot.title('Number of Friends')
    plot.xlabel('Number of Friends')
    plot.ylabel('Frequency')
    plot.grid(True)

    plot.subplot(1, 3, 2)
    seaborn.histplot(data=data, x='workHours', kde=True,
                     color='green', bins=bins_work_hours)
    plot.title('Work Hours')
    plot.xlabel('Work Hours')
    plot.ylabel('Frequency')
    plot.grid(True)

    plot.subplot(1, 3, 3)
    seaborn.histplot(data=data, x='joviality', kde=True,
                     color='red', bins=bins_joviality)
    plot.title('Joviality')
    plot.xlabel('Joviality')
    plot.ylabel('Frequency')
    plot.grid(True)

    plot.suptitle(text_on_plot)
    plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/all_in_one_histogram.png")
    if show == True:
        plot.show()
        plot.close()
    else:
        plot.close()


def plot_2(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_2: plot_pairplot")
    seaborn.set_theme(style="whitegrid")
    plot.figure(figsize=(10, 6))
    plot_kws = {'alpha': 0.8, 's': 5, 'edgecolor': 'k'}
    seaborn.pairplot(data, diag_kind='kde', plot_kws=plot_kws)
    plot.subplots_adjust(top=0.9)
    plot.suptitle(f"Pairplot: {text_on_plot}")
    plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/pairplot.png")
    if show == True:
        plot.show()
        plot.close()
    else:
        plot.close()


def plot_3(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_3: plot_pie_chart")
    categorized_dataframe = data.copy()
    bins_friends = [0, 1, 5, 10, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300, 320, 340, 360, 380, 400]
    categorized_dataframe['numberOfFriends'] = pandas.cut(
        categorized_dataframe['numberOfFriends'], bins=bins_friends)

    bins_workHours = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    categorized_dataframe['workHours'] = pandas.cut(
        categorized_dataframe['workHours'], bins=bins_workHours)
    bins_joviality = [0,  0.2, 0.4,  0.6, 0.8,  1]
    categorized_dataframe['joviality'] = pandas.cut(
        categorized_dataframe['joviality'], bins=bins_joviality)

    plot.figure(figsize=(10, 6))
    plot.subplot(1, 3, 1)
    categorized_dataframe['numberOfFriends'].value_counts().plot.pie()
    plot.title('Number of Friends')

    plot.subplot(1, 3, 2)
    categorized_dataframe['workHours'].value_counts().plot.pie()
    plot.title('Work Hours')

    plot.subplot(1, 3, 3)
    categorized_dataframe['joviality'].value_counts().plot.pie()
    plot.title('Joviality')

    plot.suptitle(text_on_plot)
    plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/all_in_one_pie_chart.png")
    if show == True:
        plot.show()
        plot.close()
    else:
        plot.close()


def plot_4(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_4: plot_quartiles")
    plot.figure(figsize=(10, 6))
    seaborn.set_theme(style="whitegrid")
    seaborn.set_context("paper", font_scale=0.8)
    seaborn.set_palette("pastel")

    plot.subplots_adjust(wspace=0.5, hspace=0.5, top=1)

    plot.subplot(1, 3, 1)
    seaborn.boxplot(data=data['numberOfFriends'], orient="v")
    plot.title('Number of Friends')

    plot.subplot(1, 3, 2)
    seaborn.boxplot(data=data['workHours'], orient="v")
    plot.title('Work Hours')

    plot.subplot(1, 3, 3)
    seaborn.boxplot(data=data['joviality'], orient="v")
    plot.title('Joviality')

    plot.suptitle(text_on_plot, fontsize=10)
    plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/quartiles.png")
    if show == True:
        plot.show()
        plot.close()
    else:
        plot.close()


def plot_5(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_5: plot_correlation_heatmap")
    plot.figure(figsize=(8, 6))
    data = data.select_dtypes(include=[numpy.number])
    seaborn.heatmap(data.corr(), annot=True, cmap='coolwarm')
    plot.title(f"Correlation Heatmap: {text_on_plot}")
    # plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/correlation_heatmap.png")
    if show == True:
        plot.show()
        plot.close()
    else:
        plot.close()


def plot_6(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_6: plot_scatter_plots")
    seaborn.pairplot(data, diag_kind='kde')
    plot.suptitle(f"Scatter Plots: {text_on_plot}")
    plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/scatter_plots.png")
    if show == True:
        plot.show()
        plot.close()
    else:
        plot.close()


def plot_7(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_7: plot_bar_plot")
    pass
    # plot.figure(figsize=(10, 6))
    # seaborn.set_theme(style="whitegrid")
    # seaborn.set_context("paper", font_scale=0.8)
    # seaborn.set_palette("pastel")

    # plot.subplot(3, 2, 1)
    # seaborn.barplot(x='numberOfFriends', y='workHours', data=data)
    # plot.title("Number of Friends vs Work Hours")

    # plot.subplot(3, 2, 2)
    # seaborn.barplot(x='numberOfFriends', y='joviality', data=data)
    # plot.title("Number of Friends vs Joviality")

    # plot.subplot(3, 2, 3)
    # seaborn.barplot(x='workHours', y='numberOfFriends', data=data)
    # plot.title("Work Hours vs Number of Friends")

    # plot.subplot(3, 2, 4)
    # seaborn.barplot(x='workHours', y='joviality', data=data)
    # plot.title("Work Hours vs Joviality")

    # plot.subplot(3, 2, 5)
    # seaborn.barplot(x='joviality', y='numberOfFriends', data=data)
    # plot.title("Joviality vs Number of Friends")

    # plot.subplot(3, 2, 6)
    # seaborn.barplot(x='joviality', y='workHours', data=data)
    # plot.title("Joviality vs Work Hours")

    # plot.suptitle(f"Bar Plot: {text_on_plot}", fontsize=10)
    # plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/bar_plot.png")
    # if show == True:
    #     plot.show()
    plot.close()
    # else:
    #     plot.close()


def plot_8(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_8: plot_line_plot")
    plot.figure(figsize=(10, 6))
    seaborn.set_theme(style="whitegrid")
    seaborn.set_context("paper", font_scale=0.8)
    seaborn.set_palette("pastel")

    plot.subplots_adjust(wspace=0.5, hspace=0.5, top=1)

    plot.subplot(2, 2, 1)
    seaborn.lineplot(x='numberOfFriends', y='workHours', data=data)
    plot.title("Work Hours vs Number of Friends")

    plot.subplot(2, 2, 2)
    seaborn.lineplot(x='numberOfFriends', y='joviality', data=data)
    plot.title("Number of Friends vs Work Hours")

    plot.subplot(2, 2, 3)
    seaborn.lineplot(x='workHours', y='numberOfFriends', data=data)
    plot.title("Work Hours vs Joviality")

    plot.subplot(2, 2, 4)
    seaborn.lineplot(x='workHours', y='joviality', data=data)
    plot.title("Number of Friends vs Joviality")

    plot.suptitle(f"Line Plot: {text_on_plot}", fontsize=10)
    plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/line_plot.png")
    if show == True:
        plot.show()
        plot.close()
    else:
        plot.close()


def plot_9(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_9: plot_density_plot")
    plot.figure(figsize=(10, 6))
    seaborn.set_theme(style="whitegrid")
    seaborn.set_context("paper", font_scale=0.8)
    seaborn.set_palette("pastel")

    plot.subplot(1, 3, 1)
    seaborn.kdeplot(data['numberOfFriends'], fill=True)
    plot.title("Density of numberOfFriends")

    plot.subplot(1, 3, 2)
    seaborn.kdeplot(data['workHours'], fill=True)
    plot.title("Density of workHours")

    plot.subplot(1, 3, 3)
    seaborn.kdeplot(data['joviality'], fill=True)
    plot.title("Density of Joviality")

    plot.title(f"Density Plot: {text_on_plot}")
    plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/density_plot.png")
    if show == True:
        plot.show()
        plot.close()
    else:
        plot.close()


def plot_10(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_10: plot_violin_plot")
    plot.figure(figsize=(10, 6))
    seaborn.set_theme(style="whitegrid")
    seaborn.set_context("paper", font_scale=0.8)
    seaborn.set_palette("pastel")

    plot.subplot(2, 2, 1)
    seaborn.violinplot(data=data, y="numberOfFriends")
    plot.title("Violin Plot: numberOfFriends")

    plot.subplot(2, 2, 2)
    seaborn.violinplot(data=data, y="workHours")
    plot.title(f"Violin Plot: Work Hours")

    plot.subplot(2, 2, 3)
    seaborn.violinplot(data=data, y="joviality")
    plot.title(f"Violin Plot: Joviality")

    plot.subplot(2, 2, 4)
    seaborn.violinplot(data=data, y="numberOfFriends", x="workHours")
    plot.title(f"Violin Plot: numberOfFriends vs Work Hours")

    plot.title(f"Violin Plot: {text_on_plot}")
    plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/violin_plot.png")
    if show == True:
        plot.show()
        plot.close()
    else:
        plot.close()


def plot_11(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_11: plot_bubble_plot")

    plot.figure(figsize=(10, 6))
    seaborn.set_theme(style="whitegrid")
    seaborn.set_context("paper", font_scale=0.8)
    seaborn.set_palette("pastel")

    plot.subplot(3, 2, 1)
    seaborn.scatterplot(data=data, x='numberOfFriends',  y='workHours',
                        size='joviality', legend=False, sizes=(20, 200))
    plot.title("numberOfFriends vs Work Hours")

    plot.subplot(3, 2, 2)
    seaborn.scatterplot(data=data, x='numberOfFriends',  y='joviality',
                        size='workHours', legend=False, sizes=(20, 200))
    plot.title(f"numberOfFriends vs Joviality")

    plot.subplot(3, 2, 3)
    seaborn.scatterplot(data=data, x='workHours',  y='numberOfFriends',
                        size='joviality', legend=False, sizes=(20, 200))
    plot.title(f"Work Hours vs numberOfFriends")

    plot.subplot(3, 2, 4)
    seaborn.scatterplot(data=data, x='workHours',  y='joviality',
                        size='numberOfFriends', legend=False, sizes=(20, 200))
    plot.title(f"Work Hours vs Joviality")

    plot.subplot(3, 2, 5)
    seaborn.scatterplot(data=data, x='joviality',  y='workHours',
                        size='numberOfFriends', legend=False, sizes=(20, 200))
    plot.title(f"Joviality vs Work Hours")

    plot.subplot(3, 2, 6)
    seaborn.scatterplot(data=data, x='joviality',  y='numberOfFriends',
                        size='workHours', legend=False, sizes=(20, 200))
    plot.title(f"Joviality vs numberOfFriends")

    plot.title(f"Bubble Plot: {text_on_plot}")
    plot.tight_layout()
    plot.xlabel('Work Hours')
    plot.ylabel('Number of Friends')
    plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/bubble_plot.png")
    if show == True:
        plot.show()
        plot.close()
    else:
        plot.close()


def plot_12(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_12: plot_scatter_plot")
    plot.figure(figsize=(10, 6))
    seaborn.set_theme(style="whitegrid")
    seaborn.set_context("paper", font_scale=0.8)
    seaborn.set_palette("pastel")
    dot_size = 5
    plot.subplot(1, 3, 1)
    seaborn.scatterplot(data=data, x='numberOfFriends',
                        y='workHours', s=dot_size)
    plot.title("numberOfFriends vs Work Hours")

    plot.subplot(1, 3, 2)
    seaborn.scatterplot(data=data, x='numberOfFriends',
                        y='joviality', s=dot_size)
    plot.title(f"numberOfFriends vs Joviality")

    plot.subplot(1, 3, 3)
    seaborn.scatterplot(data=data, x='workHours',  y='joviality', s=dot_size)
    plot.title(f"Work Hours vs Joviality")

    plot.suptitle(f"Scatter Plot: {text_on_plot}", fontsize=10)
    plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/scatter_plot.png")
    if show == True:
        plot.show()
        plot.close()
    else:
        plot.close()


def plot_13(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_13: plot_3d_scatter_plot")
    fig = plot.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    ax.scatter(data['numberOfFriends'], data['workHours'],
               data['joviality'], c='blue', marker='o')
    ax.set_xlabel('Number of Friends')
    ax.set_ylabel('Work Hours')
    ax.set_zlabel('Joviality')
    plot.title(f"3D Scatter Plot: {text_on_plot}")
    plot.tight_layout()
    if save==True:
        plot.savefig(f"{output_dir}/3d_scatter_plot.png")
    if show == True:
        plot.show()
        plot.close()
        fig.clear()
    else:
        plot.close()
        fig.clear()


def plot_14(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    print("plot_14: plot_statistics")
    file_id = text_on_plot.replace(" ", "_").replace(
        ":", "_").replace("-", "_").replace("/", "_")
    statistics = data.describe()
    agents_statistics = {}
    agents_statistics['unique_agents'] = data['agentId'].nunique()
    agents_statistics['all_agents'] = data['agentId'].count()
    agents_statistics['unique_agents_percentage'] = agents_statistics['unique_agents'] / \
        agents_statistics['all_agents'] * 100

    statistics.to_csv(f"{output_dir}/statistics.csv")
    agents_statistics = pandas.DataFrame(agents_statistics, index=[0])
    agents_statistics.to_csv(f"{output_dir}/agents_statistics.csv")

    if show == True:
        print(statistics)
        print(agents_statistics)
    else:
        print(f"Statistics are saved in {output_dir}/statistics.csv")
        print(
            f"Agents Statistics are saved in {output_dir}/agents_statistics.csv")


def plot_15(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    pass


def plot_16(data, text_on_plot, output_dir="./results/plots", show=False, save=True):
    pass
