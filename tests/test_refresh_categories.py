"""Tests for scripts/refresh_categories.py helper functions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from refresh_categories import build_category_tree, flatten_tree

DUPLICATE_NAME_TREE = [
    {
        "name": "毒品犯罪",
        "id": "001006007",
        "children": [
            {"name": "毒品犯罪", "id": "001006007001", "children": []},
            {"name": "非法持有毒品罪", "id": "001006007002", "children": []},
        ],
    }
]

MOCK_TREE = [
    {
        "name": "刑事",
        "id": "001",
        "children": [
            {
                "name": "危害公共安全罪",
                "id": "001002",
                "children": [
                    {"name": "放火罪", "id": "001002001", "children": []},
                    {"name": "交通肇事罪", "id": "001002037", "children": []},
                ],
            },
            {
                "name": "破坏社会主义市场经济秩序罪",
                "id": "001003",
                "children": [
                    {
                        "name": "扰乱市场秩序罪",
                        "id": "001003008",
                        "children": [
                            {
                                "name": "合同诈骗罪",
                                "id": "001003008004",
                                "children": [],
                            },
                        ],
                    },
                    {
                        "name": "金融诈骗罪",
                        "id": "001003005",
                        "children": [
                            {
                                "name": "信用卡诈骗罪",
                                "id": "001003005006",
                                "children": [],
                            },
                        ],
                    },
                ],
            },
        ],
    }
]


class TestFlattenTree:
    def test_top_level(self):
        result = flatten_tree(MOCK_TREE)
        assert result["刑事"] == "001"

    def test_second_level(self):
        result = flatten_tree(MOCK_TREE)
        assert result["危害公共安全罪"] == "001002"

    def test_third_level(self):
        result = flatten_tree(MOCK_TREE)
        assert result["放火罪"] == "001002001"
        assert result["交通肇事罪"] == "001002037"

    def test_fourth_level(self):
        result = flatten_tree(MOCK_TREE)
        assert result["合同诈骗罪"] == "001003008004"
        assert result["信用卡诈骗罪"] == "001003005006"

    def test_entry_count(self):
        result = flatten_tree(MOCK_TREE)
        # 刑事, 危害公共安全罪, 放火罪, 交通肇事罪,
        # 破坏社会主义市场经济秩序罪, 扰乱市场秩序罪, 合同诈骗罪,
        # 金融诈骗罪, 信用卡诈骗罪
        assert len(result) == 9

    def test_empty_children(self):
        result = flatten_tree([{"name": "leaf", "id": "123", "children": []}])
        assert result == {"leaf": "123"}

    def test_no_children_key(self):
        result = flatten_tree([{"name": "leaf", "id": "456"}])
        assert result == {"leaf": "456"}

    def test_duplicate_name_parent_wins(self):
        result = flatten_tree(DUPLICATE_NAME_TREE)
        assert result["毒品犯罪"] == "001006007"


class TestBuildCategoryTree:
    def test_top_level_has_id_and_children(self):
        result = build_category_tree(MOCK_TREE)
        assert "刑事" in result
        assert result["刑事"]["id"] == "001"
        assert "children" in result["刑事"]

    def test_nested_children(self):
        result = build_category_tree(MOCK_TREE)
        assert "危害公共安全罪" in result["刑事"]["children"]

    def test_leaf_is_string_id(self):
        result = build_category_tree(MOCK_TREE)
        assert (
            result["刑事"]["children"]["危害公共安全罪"]["children"]["放火罪"]
            == "001002001"
        )

    def test_fourth_level_tree(self):
        result = build_category_tree(MOCK_TREE)
        l3 = result["刑事"]["children"]["破坏社会主义市场经济秩序罪"]["children"][
            "扰乱市场秩序罪"
        ]
        assert l3["id"] == "001003008"
        assert l3["children"]["合同诈骗罪"] == "001003008004"

    def test_empty_input(self):
        assert build_category_tree([]) == {}
