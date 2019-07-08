import dash
import dash_core_components as dcc
import dash_html_components as html
import math
import numpy as np
from scipy.special import wofz
import plotly.graph_objs as go
import plotly.tools as tls
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from pymatgen import MPRester
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from pymatgen.electronic_structure.plotter import BSPlotter
from pymatgen.electronic_structure.core import Spin

from crystal_toolkit.helpers.layouts import *
from crystal_toolkit.components.core import MPComponent, PanelComponent

# Author: Jason Munro
# Contact: jmunro@lbl.gov


class BandstructureAndDosComponent(MPComponent):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.create_store("mpid")

    empty_plot_style = {
        "xaxis": {"visible": False},
        "yaxis": {"visible": False},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
    }

    @property
    def all_layouts(self):

        # Main plot
        graph = html.Div(
            [
                dcc.Graph(
                    figure=go.Figure(
                        layout=BandstructureAndDosComponent.empty_plot_style),
                    config={"displayModeBar": False},
                )
            ], id=self.id("bsdos-div")
        )

        return {"graph": graph}

    @property
    def standard_layout(self):
        return html.Div([
            Column([
                self.all_layouts["graph"]
            ], size=8),
        ])

    def _generate_callbacks(self, app, cache):
        @app.callback(Output(self.id("bsdos-div"), "children"),
                      [
                      Input(self.id(), "data"),
                      ])
        def update_graph(data):

            if not data:
                search_error = MessageContainer(
                    [
                        MessageBody(
                            dcc.Markdown(
                                "Band structure and density of states not available for this selection."
                            )
                        ),
                    ],
                    kind="warning",
                ),
                return search_error

            figure = tls.make_subplots(rows=1, cols=2, shared_yaxes=True, print_grid=False)

            bstraces, dostraces, bs_data = data

            # -- Add trace data to plots
            for bstrace in bstraces:
                figure.append_trace(bstrace, 1, 1)

            for dostrace in dostraces:
                figure.append_trace(dostrace, 1, 2)

            xaxis_style = go.layout.XAxis(
                title=dict(text='Wave Vector',
                           font=dict(size=16)),
                tickmode='array',
                tickvals=bs_data['ticks']['distance'],
                ticktext=bs_data['ticks']['label'],
                tickfont=dict(size=16),
                ticks="inside",
                tickwidth=2,
                showgrid=True,
                showline=True,
                linewidth=2,
                mirror=True)

            yaxis_style = go.layout.YAxis(
                title=dict(text='E-Efermi (eV)',
                           font=dict(size=16)),
                tickfont=dict(size=16),
                showgrid=True,
                showline=True,
                zeroline=True,
                mirror="ticks",
                ticks="inside",
                linewidth=2,
                tickwidth=2,
                zerolinewidth=2,
                range=[-5, 5])

            xaxis_style_dos = go.layout.XAxis(
                title=dict(text='Density of States',
                           font=dict(size=16)),
                tickfont=dict(size=16),
                showgrid=True,
                showline=True,
                mirror=True,
                ticks="inside",
                linewidth=2,
                tickwidth=2)

            layout = go.Layout(
                title="",
                xaxis1=xaxis_style,
                xaxis2=xaxis_style_dos,
                yaxis=yaxis_style,
                showlegend=True,
                height=500,
                width=1500,
                hovermode='x',
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=60, b=50, t=50, pad=0, r=30)
            )

            figure["layout"].update(layout)

            legend = go.layout.Legend(
                x=1.0, y=.98,
                xanchor="left", yanchor="top",
                bordercolor='#333', borderwidth=1,
                traceorder='normal')

            figure["layout"]["legend"] = legend

            figure["layout"]["xaxis1"]["domain"] = [0., 0.6]
            figure["layout"]["xaxis2"]["domain"] = [0.65, 1.0]

            return [dcc.Graph(figure=figure, config={"displayModeBar": False})]

        @app.callback(
            Output(self.id(), "data"),
            [Input(self.id("mpid"), "data")])
        def bs_dos_data(mpid):

            # -- Bandstructure Data
            bstraces = []

            if not mpid or "mpid" not in mpid:
                raise PreventUpdate

            mpid = mpid["mpid"]

            with MPRester() as m:
                bs = m.get_bandstructure_by_material_id(mpid)
                dos = m.get_dos_by_material_id(mpid)

            if not bs or not dos:
                raise PreventUpdate

            bs_reg_plot = BSPlotter(bs)

            bs_data = bs_reg_plot.bs_plot_data()

            # -- Strip latex math wrapping
            for entry_num in range(len(bs_data['ticks']['label'])):

                bs_data['ticks']['label'][entry_num] = \
                    bs_data['ticks']['label'][entry_num].replace('$', '')

                bs_data['ticks']['label'][entry_num] = \
                    bs_data['ticks']['label'][
                        entry_num].replace(r'\mid', '|')

                bs_data['ticks']['label'][entry_num] = \
                    bs_data['ticks']['label'][
                        entry_num].replace(r'\Gamma', 'Γ')

            for d in range(len(bs_data['distances'])):
                for i in range(bs_reg_plot._nb_bands):
                    bstraces.append(go.Scatter(
                        x=bs_data['distances'][d],
                        y=[bs_data['energy'][d][str(Spin.up)][i][j]
                           for j in range(len(bs_data['distances'][d]))],
                        mode='lines',
                        line=dict(color=("#666666"),
                                  width=2),
                        hoverinfo='skip',
                        showlegend=False),
                    )

                    if bs_reg_plot._bs.is_spin_polarized:
                        bstraces.append(
                            go.Scatter(
                                x=bs_data['distances'][d],
                                y=[bs_data['energy'][d][str(Spin.down)][i][j]
                                    for j in range(len(bs_data['distances'][d]))],
                                mode='lines',
                                line=dict(color=("#666666"),
                                          width=2,
                                          dash='dash'),
                                hoverinfo='skip',
                                showlegend=False),
                        )

            # -- DOS Data
            dostraces = []

            if bs_reg_plot._bs.is_spin_polarized:
                # Add second spin data if available
                trace_tdos = go.Scatter(
                    x=dos.densities[Spin.down],
                    y=dos.energies - dos.efermi,
                    mode="lines",
                    name="Total DOS (spin ↓)",
                    line=go.scatter.Line(color="#444444", dash='dash'),
                    fill="tozeroy",
                )

                dostraces.append(trace_tdos)

                tdos_label = "Total DOS (spin ↑)"
            else:
                tdos_label = "Total DOS"

            # Total DOS
            trace_tdos = go.Scatter(
                x=dos.densities[Spin.up],
                y=dos.energies - dos.efermi,
                mode="lines",
                name=tdos_label,
                line=go.scatter.Line(color="#444444"),
                fill="tozeroy",
                legendgroup='spinup'
            )

            dostraces.append(trace_tdos)

            p_ele_dos = dos.get_element_dos()

            # Projected data
            count = 0
            colors = [
                '#1f77b4',  # muted blue
                '#ff7f0e',  # safety orange
                '#2ca02c',  # cooked asparagus green
                '#d62728',  # brick red
                '#9467bd',  # muted purple
                '#8c564b',  # chestnut brown
                '#e377c2',  # raspberry yogurt pink
                '#bcbd22',  # curry yellow-green
                '#17becf'   # blue-teal
            ]

            for ele in p_ele_dos.keys():

                if bs_reg_plot._bs.is_spin_polarized:
                    trace = go.Scatter(
                        x=p_ele_dos[ele].densities[Spin.down],
                        y=dos.energies - dos.efermi,
                        mode="lines",
                        name=ele.symbol + ' (spin ↓)',
                        line=dict(width=3, color=colors[count], dash='dash'),
                    )

                    dostraces.append(trace)
                    spin_up_label = ele.symbol + ' (spin ↑)'

                else:
                    spin_up_label = ele.symbol

                trace = go.Scatter(
                    x=p_ele_dos[ele].densities[Spin.up],
                    y=dos.energies - dos.efermi,
                    mode="lines",
                    name=spin_up_label,
                    line=dict(width=3, color=colors[count]),
                )

                dostraces.append(trace)

                count += 1

            data = [bstraces, dostraces, bs_data]

            return data


class BandstructureAndDosPanelComponent(PanelComponent):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bs = BandstructureAndDosComponent()
        self.bs.attach_from(self, this_store_name="mpid")

    @property
    def title(self):
        return "Band Structure and Density of States"

    @property
    def description(self):
        return "Display the band structure and density of states for this structure \
        if it has been calculated by the Materials Project."

    @property
    def initial_contents(self):
        return html.Div(
            [
                super().initial_contents,
                html.Div([self.bs.standard_layout], style={"display": "none"}),
            ]
        )

    def update_contents(self, new_store_contents, *args):
        return self.bs.standard_layout
