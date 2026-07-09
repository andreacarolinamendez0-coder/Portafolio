"""
visualizar_red.py
=================
Genera una imagen PNG del grafo de riesgo con TUS datos reales.
Corre esto en la carpeta Portafolio, junto a preparador_datos.py y red_riesgo.py.

Requiere matplotlib:
    pip install matplotlib
"""

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import networkx as nx

from preparador_datos import preparar_universo
from red_riesgo import construir_grafo_completo
from networkx.algorithms.community import louvain_communities, modularity


def visualizar(resolution=1.0, umbral_ruido=0.05, guardar_como="red_riesgo_real.png"):
    datos = preparar_universo()
    corr = datos["correlacion"]

    G = construir_grafo_completo(corr, umbral_ruido)
    comunidades = louvain_communities(G, weight="weight", resolution=resolution, seed=42)
    mod = modularity(G, comunidades, weight="weight")

    print(f"Comunidades: {len(comunidades)} | Modularidad: {mod:.4f}")

    # Paleta — se extiende sola si hay más comunidades que colores
    paleta = ['#4CC9F0', '#F72585', '#FFD60A', '#06FFA5', '#B5179E',
              '#F77F00', '#7209B7', '#80FFDB', '#FF6B6B', '#A0C4FF']
    color_nodo = {}
    for idx, com in enumerate(comunidades):
        for n in com:
            color_nodo[n] = paleta[idx % len(paleta)]

    fig, ax = plt.subplots(figsize=(18, 18), facecolor='#0a0e1a')
    ax.set_facecolor('#0a0e1a')

    # spring_layout usa el peso: activos correlacionados se atraen
    pos = nx.spring_layout(G, k=0.55, iterations=120, seed=42, weight='weight')

    for (u, v, d) in G.edges(data=True):
        w = d['weight']
        ax.plot([pos[u][0], pos[v][0]], [pos[u][1], pos[v][1]],
                color='#2a3a5a', alpha=min(w * 0.5, 0.4),
                linewidth=w * 1.2, zorder=1)

    for n in G.nodes():
        ax.scatter(pos[n][0], pos[n][1], s=650, c=color_nodo[n],
                   edgecolors='white', linewidths=1.2, zorder=2, alpha=0.9)
        ax.text(pos[n][0], pos[n][1], n, fontsize=7, ha='center', va='center',
                color='#0a0e1a', fontweight='bold', zorder=3)

    leyenda = [
        Patch(facecolor=paleta[i % len(paleta)], edgecolor='white',
              label=f"Comunidad {i + 1} ({len(com)} activos)")
        for i, com in enumerate(comunidades)
    ]
    ax.legend(handles=leyenda, loc='upper left', fontsize=12,
              facecolor='#131a2e', edgecolor='#2a3a5a',
              labelcolor='white', framealpha=0.9)

    ax.set_title(
        f'Red de Riesgo del Portafolio — {len(comunidades)} comunidades '
        f'(resolution={resolution}, modularidad={mod:.3f})',
        fontsize=18, color='white', pad=20, fontweight='bold'
    )
    ax.axis('off')
    plt.tight_layout()
    plt.savefig(guardar_como, dpi=130, facecolor='#0a0e1a', bbox_inches='tight')
    print(f"Imagen guardada como {guardar_como}")


if __name__ == "__main__":
    visualizar()