import logging
import unittest
import numpy as np
import pandas as pd
from rad.rad import IsolationForest, IsolationTree, TreeScore

from rad import rad


# disable logging unless error is significant
logging.disable(logging.ERROR)


class TestC(unittest.TestCase):
    """
    Test behavior of the average length of an unsuccessful binary search, c.
    """

    def test_negative_length_throws_exception(self):
        n = np.random.randint(-1000, 0)
        self.assertRaises(ValueError, rad.c, n)

    def test_positive_length_gives_positive_c(self):
        n = np.random.randint(1, 1000)
        self.assertTrue(rad.c(n) >= 1)


class TestS(unittest.TestCase):
    """
    Test behavior of the scoring function, s. We define `x` as the depth of the
    respective node, and `s` as the number of instances (`sample_size`).
    """

    def test_small_x_small_n_is_anomaly(self):

        # limit(x -> 0) and limit(n -> 0) => anomaly; node is near the top
        x = np.random.randint(0, 3)
        n = np.random.randint(5, 10)
        self.assertTrue(rad.s(x=x, n=n) >= .5)

    def test_small_x_large_n_is_anomaly(self):

        # limit(x -> 0) and limit(n -> inf) => anomaly; node if near the top
        x = np.random.randint(0, 3)
        n = np.random.randint(50, 1000)
        self.assertTrue(rad.s(x=x, n=n) >= .5)

    def test_large_x_large_n_is_normal(self):

        # limit(x -> inf) and limit(n -> inf) => normal; node is far down
        x = np.random.randint(10, 1000)
        n = np.random.randint(50, 1000)
        self.assertTrue(rad.s(x=x, n=n) <= .5)

    def test_large_x_small_n_is_normal(self):

        # limit(x -> 0) and limit(n -> inf) => normal; node is far down
        x = np.random.randint(10, 1000)
        n = np.random.randint(50, 100)
        self.assertTrue(rad.s(x=x, n=n) <= .5)


class TestPreprocess(unittest.TestCase):

    def setUp(self):
        size = np.random.randint(1, 100, size=2)
        data = np.random.randint(-100000, 100000, size)
        self.frame = pd.DataFrame(data)

    def test_preprocess_doesnt_change_numeric_array(self):
        frame, _ = rad.preprocess(self.frame)
        # numeric arrays, after `preprocess`, are exactly the same as before.
        self.assertEqual(frame.values.all(), self.frame.values.all())

    def test_empty_mapping_given_numeric_array(self):
        """
        Test that if a numeric array is given, no mappings are returned.
        """
        _, mapping = rad.preprocess(self.frame)
        self.assertEqual(len(mapping), 0)

    def test_populated_mapping_given_nonnumeric_array(self):
        """
        Test that all string columns get mapped to its respective integer.
        """
        shape = (len(self.frame), np.random.randint(1, 5))
        nd_array = np.random.choice(["a", "b"], shape)
        frame, mapping = rad.preprocess(nd_array)
        self.assertEqual(len(mapping), nd_array.shape[1])

    def test_invalid_column_as_index_raises_keyerror(self):
        """
        Test that an invalid column cannot be set as the index
        """
        self.assertRaises(KeyError, rad.preprocess, self.frame, ["invalid"])

    def test_valid_column_set_as_index(self):
        """
        Test that the index is a valid column name
        """
        column = np.random.choice(self.frame.columns.values)
        frame, mapping = rad.preprocess(self.frame, index=column)
        self.assertEqual(frame.index.name, column)


class TestPreprocessOn(unittest.TestCase):

    def setUp(self):
        size = np.random.randint(1, 100, size=2)
        data = np.random.randint(-100000, 100000, size)
        self.frame = pd.DataFrame(data)
        self.frame["groups"] = np.random.choice(["a", "b"], len(self.frame))

    def test_preprocess_on_output_equals_num_groups(self):
        """
        Test that the number of chunks from `preprocess_on` equals the number
        of groups, i.e. ["A", "B", "C", ...]
        """
        uniq_groups = np.unique(self.frame["groups"])
        chunks = rad.preprocess_on(self.frame, on="groups", min_records=0)
        self.assertEqual(len(chunks), len(uniq_groups))

    def test_preprocess_on_group_must_exist(self):
        """
        Test that an invalid column set for `on` raises KeyError exception
        """
        self.assertRaises(KeyError, rad.preprocess_on, self.frame, "bad column")


class TestIsolationForest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """
        Building an IsolationForest *can* be expensive, so do it only once
        """
        cls.size = np.random.randint(10, 100, size=2)
        cls.data = np.random.randint(0, 1000, size=cls.size)
        cls.forest = IsolationForest(cls.data)
        cls.forest.predict(cls.data)

    def test_correct_number_of_trees_made(self):
        """
        Test that if N trees are desired, N trees shall be made
        """
        self.assertEqual(self.forest.num_trees, len(self.forest.trees))

    def test_predict_length_equals_input_length(self):
        """
        Test that each input record has a corresponding prediction
        """
        out = self.forest.predict(self.data)
        self.assertEqual(len(out), len(self.data))

    def test_predict_contains_score(self):
        """
        Test that the `predict` JSON contains a `score` key
        """
        arr = self.forest.predict(self.data)
        has_score = list(map(lambda x: "score" in x, arr))
        self.assertTrue(all(has_score))

    def test_predict_contains_depth(self):
        """
        Test that the `predict` JSON contains a `depth` key
        """
        arr = self.forest.predict(self.data)
        has_depth = list(map(lambda x: "depth" in x, arr))
        self.assertTrue(all(has_depth))

    def test_predict_score_max_is_one(self):
        """
        Test `predict` scores maximum is 1
        """
        arr = self.forest.predict(self.data)
        score_lt_one = list(map(lambda x: x["score"] <= 1, arr))
        self.assertTrue(all(score_lt_one))

    def test_predict_score_min_is_zero(self):
        """
        Test `predict` scores minimum is 0
        """
        arr = self.forest.predict(self.data)
        score_gt_zero = list(map(lambda x: x["score"] >= 0, arr))
        self.assertTrue(all(score_gt_zero))

    def test_predict_with_one_index_has_one_id(self):
        """
        Test giving a basic ndarray or DataFrame, void of index.name, a default
        `index.name := id` is set.
        """
        arr = self.forest.predict(self.data)
        has_id = list(map(lambda x: "id" in x, arr))
        self.assertTrue(all(has_id))

    def test_real_positive_anomaly_is_predicted(self):
        """
        Test that really-large values are labeled as anomalies
        """
        data = np.repeat(np.finfo(float).max, self.size[1])
        data = np.reshape(data, (1, self.size[1]))
        anom = list(map(lambda x: x["is_anomalous"], self.forest.predict(data)))
        self.assertTrue(all(anom))

    def test_real_negative_anomaly_is_predicted(self):
        """
        Test that really-large values are labeled as anomalies
        """
        data = np.repeat(np.finfo(float).min, self.size[1])
        data = np.reshape(data, (1, self.size[1]))
        anom = list(map(lambda x: x["is_anomalous"], self.forest.predict(data)))
        self.assertTrue(all(anom))


class TestIsolationTree(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """
        Building an IsolationTree is less expensive than forest, but do it once
        """
        size = np.random.randint(10, 50, size=2)
        data = np.random.randint(0, 10000, size=size)
        cls.tree = IsolationTree(data, depth=1, limit=10)

    def test_tree_built_some_nodes(self):
        """
        Test that an IsolationTree has a positive number of nodes
        """
        num_nodes = self.tree.num_internal_nodes + self.tree.num_external_nodes
        self.assertTrue(num_nodes > 0)

    def test_random_value_in_column(self):
        """
        Test that given a column, q, a random number, p, falls within its range.
        """
        column = self.tree.data[:, self.tree._pos]
        self.assertTrue(min(column) <= self.tree._value <= max(column))

    def test_random_value_within_column(self):
        """
        Test that the `Node` attribute, `value`, falls between a columns range.
        """
        node = self.tree.root
        min_ = min(node.data[:, node.pos])
        max_ = max(node.data[:, node.pos])
        self.assertTrue(min_ <= node.value <= max_)

    def test_root_has_max_two_nodes(self):
        """
        Test that the root-Node object has a maximum of two Nodes
        """
        root = self.tree.root
        left = root.left is not None
        right = root.right is not None
        self.assertTrue(sum([left, right]) <= 2)

    def test_internal_node_has_children(self):
        """
        Test than an internal node must have two Node instances.
        """
        left = self.tree.root.left is not None
        right = self.tree.root.right is not None
        truth = all([left, right, self.tree.root.type == "internal"])
        self.assertTrue(truth)


class TestTreeScore(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        size = np.random.randint(10, 50, size=2)
        cls.data = np.random.randint(0, 1000, size=size)
        cls.tree = IsolationTree(cls.data, depth=1, limit=10)

    def test_path_is_not_negative(self):
        """
        Test that the depth is positive
        """
        vector = np.random.random(self.data.shape[1])
        scorer = TreeScore(vector, self.tree)
        self.assertTrue(scorer.path >= 0)


if __name__ == '__main__':
    unittest.main()
