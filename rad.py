"""
Red Hat Anomaly Detection, or RAD, is a python module for performing various
anomaly detection tasks in-support of the AI-ops effort. RAD leverages the
Isolation Forest (IF) ensemble data-structure; a class that partitions a
data-set and leverages such slicing to gauge magnitude of anomaly. In other
words, the more partitions, the more "normal" the record.
Much of the algorithms in this module are from the works of Liu et al.
(https://cs.nju.edu.cn/zhouzh/zhouzh.files/publication/icdm08b.pdf)
"""


import os
import s3fs
import pickle
import urllib3
import logging
import requests
import numpy as np
import pandas as pd

from pyarrow import parquet
from requests.auth import HTTPBasicAuth
from collections import namedtuple


__version__ = "0.8.2"


def fetch_s3(bucket, profile_name=None, folder=None, date=None,
             endpoint=None, workers=None):
    """
    Queries data collected from Insights that is saved in S3. It is presumed
    `profile_name` (your ~/.aws/credentials name) exhibits credentials to
    facilitate such an access.

    Args:
         endpoint (str): S3 endpoint.
         profile_name (str): AWS credentials; found in ~/.aws/credentials
         bucket (str): S3 bucket name.
         folder (str): folder name; contains many parquet files
         date (str): S3 prefix; is that which is prepended to `bucket`.
         workers (int): maximum number of worker threads.
    """
    if not profile_name:
        profile_name = "default"

    if not endpoint:
        endpoint = "https://s3.upshift.redhat.com"

    if not date:
        date = ""

    if not folder:
        folder = ""

    fs = s3fs.S3FileSystem(profile_name=profile_name,
                           client_kwargs={"endpoint_url": endpoint})

    # concatenate the bucket and all subsequent variables to give a full path
    path = os.path.join(bucket, date, folder)
    obj = parquet.ParquetDataset(path, fs, metadata_nthreads=workers)
    frame = obj.read_pandas().to_pandas()
    return frame


def fetch_inventory_data(email, password, url=None):
    """
    Trivial function to fetch some Host Inventory Data.

    Args:
        email (str): user authentication key.
        password (str): password; defaults to `redhat`
        url (str): endpoint for the host inventory data.

    Returns:
        dict following retrieval from the Host Inventory API.

    Examples:
        >>> dic = fetch_inventory_data()
    """
    if url is None:
        url = "https://ci.cloud.paas.upshift.redhat.com/api/inventory/v1/hosts"

    # it is presumed certificates are not needed to access the URL
    urllib3.disable_warnings()
    resp = requests.get(url, auth=HTTPBasicAuth(email, password), verify=False)
    return resp.json()


def inventory_data_to_pandas(dic):
    """
    Parse a JSON object, fetched from the Host Inventory Service, and massage
    the data to serve as a pandas DataFrame. We define rows of this DataFrame
    as unique `display_name` instances, and individual column names being an
    individual "system fact" keyword within the `facts` key. Each row-column
    cell is the value for said system-fact.

    Args:
        dic (dict): dictionary from `fetch_fetch_inventory_data(...)`

    Returns:
        DataFrame: each column is a feature and its cell is its value.

    Examples:
        >>> dic = fetch_inventory_data()  # provide your specific credentials
        >>> frame = inventory_data_to_pandas(dic)
    """

    # keep track of systems lacking data; useful for finding anomalous signals
    lacks_data = []

    # list of dictionary items for each and every row
    rows = []

    # iterate over all records; all data resides under the `results` key
    for result in dic["results"]:

        # assert that `facts` and `account` are keys, otherwise throw error
        if "facts" not in result:
            raise IOError("JSON must contain `facts` key under `results`")
        if "account" not in result:
            raise IOError("JSON must contain `account` key under `results`")

        # get some preliminary data
        data = result["facts"]
        name = result["display_name"]

        # identify systems which lack data
        if len(data) == 0:
            lacks_data.append(name)
            continue

        # data looks like this:
        # [{'facts': {'fqdn': 'eeeg.lobatolan.home'}, 'namespace': 'inventory'}]

        # iterate over all the elements in the list; usually gets one element
        for dic in data:
            if not isinstance(dic, dict):
                raise IOError("Data elements must be dict")

            if "facts" not in dic:
                raise KeyError("`facts` key must reside in the dictionary")

            # iterate over all the key-value pairs
            for k, v in dic["facts"].items():

                # handling numeric values
                if isinstance(v, (int, bool)):
                    v = float(v)
                    rows.append({"ix": name, "value": v, "col": k})

                # if a collection, each collection item is its own feature
                elif isinstance(v, (list, tuple)):
                    for v_ in v:
                        rows.append({"ix": name,
                                     "value": True,
                                     "col": "{}|{}".format(k, v_)})

                # handling strings is trivial
                elif isinstance(v, str):
                    rows.append({"ix": name,
                                 "value": v,
                                 "col": k})

                # sometimes, values are `dict`, so handle accordingly
                elif isinstance(v, dict):
                    for k_, v_ in v.items():
                        rows.append({"ix": name,
                                     "value": v_,
                                     "col": "{}".format(k_)})

                # end-case; useful if value is None or NaN
                else:
                    rows.append({"ix": name, "value": -1, "col": k})

    # take all the newly-added data and make it into a DataFrame
    frame = pd.DataFrame(rows).drop_duplicates()

    # add all the data that lack values
    for id_ in lacks_data:
        frame = frame.append(pd.Series({"ix": id_}), ignore_index=True)

    frame = frame.pivot(index="ix", columns="col", values="value")
    return frame.drop([np.nan], axis=1)


def preprocess(frame, index=None, drop=None):
    """
    Performs important DataFrame pre-processing so that indices can be set,
    columns can be dropped, or non-numeric columns be encoded as their
    equivalent numeric.

    Args:
        frame (DataFrame): pandas DataFrame.
        index (str or list): columns to serve as DataFrame index.
        drop (str or list): columns to drop from the DataFrame.

    Returns:
         DataFrame and dict: processed DataFrame and encodings of its columns.
    """

    # copy the frame so the original is not overwritten
    df = pd.DataFrame(frame)

    try:
        # set the index to be something that identifies each row
        if index is not None:
            df.set_index(index, inplace=True)

        # drop some spurious columns, i.e. `upload_time`
        if drop is not None:
            df.drop(drop, axis=1, inplace=True)

        # encode non-numeric columns as integer; datetimes are not `object`
        mappings = {}
        for column in df.select_dtypes(include=(object, bool)):

            # convert the non-numeric column as categorical and overwrite column
            category = df[column].astype("category")
            df[column] = category.cat.codes.astype(float)

            # column categories and add mapping, i.e. "A" => 1, "B" => 2, etc.
            cats = category.cat.categories
            mappings[column] = dict(zip(cats, range(len(cats))))

        # remove all remaining columns, i.e. `datetime`
        df = df.select_dtypes(include=np.number)

        # return the DataFrame and categorical mappings
        return df, mappings
    except KeyError:
        logging.error("`index` or `drop` must exist as columns.")
        return pd.DataFrame(), {}


def preprocess_on(frame, on, min_records=50, index=None, drop=None):
    """
    Similar to `preprocess` but groups records in the DataFrame on a group pf
    features. Each respective chunk or block is then added to a list; analogous
    to running `preprocess` on a desired subset of a DataFrame.

    Args:
        frame (DataFrame): pandas DataFrame
        on (str or list): features in `frame` you wish to group around.
        min_records (int): minimum number of rows each grouped chunk must have.
        index (str or list): columns to serve as DataFrame index.
        drop (str or list): columns to drop from the DataFrame.

    Returns:
         DataFrame and dict: processed DataFrame and encodings of its columns.
    """
    try:
        # data, mapping = preprocess(frame, index=index, drop=drop)

        data = pd.DataFrame(frame)
        out = []

        # group-by `on` and return the chunks which satisfy minimum length
        for _, chunk in data.groupby(on):
            if len(chunk) > min_records:

                # if only `on` is provided, set this as the index
                if index is None and on is not None:
                    index = on

                # run `preprocess` on each chunk
                chunk, mapping = preprocess(chunk, index=index, drop=drop)
                out.append((chunk, mapping))
        return out

    except KeyError:
        logging.error("`on` must exist in either index-name or column(s).")