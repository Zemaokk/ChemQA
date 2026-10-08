import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from src.knowledge_base.retriever import Retriever
from src.knowledge_base.similarity import top_indices


class HeatmapVisualizer:
    def __init__(self):
        """初始化热力图可视化器"""
        self.retriever = Retriever()

    def generate_organic_electrocatalysis_queries(self) -> list[str]:
        """
        生成5个与有机电催化相关的英文查询

        Returns:
            查询文本列表
        """
        queries = [
            "mechanism of CO2 electroreduction on Cu single-atom catalysts",
            "electrochemical oxidation of alcohols to aldehydes",
            "electrochemical C-H functionalization of arenes",
            "electrochemical synthesis of heterocyclic compounds",
            "electrochemical reduction of carbonyl compounds",
        ]
        return queries

    def prepare_similarity_data(self, queries: list[str], max_docs: int = 15) -> dict:
        """Use retrieval scores; select rows by mean cosine across supplied queries."""
        if not queries:
            raise ValueError("At least one query is required for a similarity heatmap")
        top_indices(np.empty(0), max_docs)
        store = self.retriever.vector_store
        documents = store.vector_index.get("documents", [])
        if not documents or max_docs == 0:
            matrix = np.empty((0, len(queries)))
            selected = np.empty(0, dtype=int)
        else:
            matrix = np.column_stack([store.score_query(query) for query in queries])
            selected = top_indices(matrix.mean(axis=1), max_docs)
        chosen = [documents[i] for i in selected]
        return {
            "queries": list(queries),
            "metric": "cosine",
            "matrix": matrix,
            "selected_indices": selected,
            "selected_matrix": matrix[selected],
            "documents": chosen,
            "chunk_ids": [d["chunk_id"] for d in chosen],
        }

    def create_similarity_heatmap(
        self,
        queries: list[str] | None = None,
        max_docs: int = 15,  # 显示前15个最相关文档
        figsize: tuple = (12, 8),
        cmap: str = "viridis",  # 改为viridis以提高区分度
        vmin: float = -1.0,
        vmax: float = 1.0,
        save_path: str | None = None,
    ) -> None:
        """
        创建查询-文档相似度热力图

        Args:
            queries: 查询文本列表，如果为None则使用默认的有机电催化查询
            max_docs: 显示的最相关文档数量
            figsize: 图像大小
            cmap: 颜色映射
            vmin: 颜色映射最小值
            vmax: 颜色映射最大值
            save_path: 保存图像的路径，如果为None则显示图像
        """
        # 如果没有提供查询，使用默认的有机电催化查询
        if queries is None:
            queries = self.generate_organic_electrocatalysis_queries()

        data = self.prepare_similarity_data(queries, max_docs)
        selected_similarity_matrix = data["selected_matrix"]
        if not len(data["documents"]):
            print("No chunks selected for the similarity heatmap")
            return
        doc_labels = [f"Chunk{i + 1}" for i in range(len(data["documents"]))]

        # 设置matplotlib字体大小
        plt.rcParams.update({"font.size": 18})  # 进一步增大默认字体大小

        # 创建热力图
        plt.figure(figsize=figsize)

        # 创建热力图，纵轴显示chunk编号
        sns.heatmap(
            selected_similarity_matrix,
            xticklabels=[f"Q{i + 1}" for i in range(len(queries))],
            yticklabels=doc_labels,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            annot=True,
            fmt=".2f",
            annot_kws={"size": 16},  # 进一步增大注释文字大小
            cbar_kws={"label": "Cosine Similarity"},
        )

        # 设置标题和标签（进一步增大字号）
        plt.title(
            "Query-Chunk Cosine Similarity",
            fontsize=24,
            fontweight="bold",
        )
        plt.xlabel("Queries", fontsize=20)
        plt.ylabel("Text Chunks", fontsize=20)

        # 进一步增大刻度标签字号
        plt.xticks(fontsize=18)
        plt.yticks(fontsize=18)

        # 进一步增大颜色条标签字号
        cbar = plt.gcf().axes[-1]
        cbar.set_ylabel("Cosine Similarity", fontsize=20)
        cbar.tick_params(labelsize=18)

        # 调整布局
        plt.tight_layout()

        # 保存或显示图像
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            print(f"Heatmap saved to: {save_path}")
        else:
            plt.show()

        # 打印查询详情
        print("\nQuery Details:")
        for i, query in enumerate(queries):
            print(f"Q{i + 1}: {query}")

        # 打印文档详情
        print("\nChunk Details:")
        for i, doc in enumerate(data["documents"]):
            print(f"Chunk{i + 1}: {doc.get('title') or doc.get('source', '')}")
            print(
                f"  chunk_id: {doc['chunk_id']}; PDF pages: {doc.get('page_numbers', [])}"
            )
        plt.close()
