from gtab import GTAB
import hydra
from loguru import logger
from omegaconf import DictConfig
import orjson
from pathlib import Path
import pandas as pd
from typing import List
from tqdm import tqdm
import sys

from utils import get_predator_list
from negative_search import NegativeKW_Collector


class TrendSearch():
    def __init__(self, 
                 predator_list: List[str], 
                 suffix: str = "Sexual harassment",
                 geo: str = "", 
                 period: List[str] = ["2016-01-01", "2018-07-31"],
                 n_url: int = 20,
                 search_sleep: int = 10,
                 sentiment_model: str = "sentiment",
                 extract_model: str = "Voicelab/vlt5-base-keywords"
                 ):
        invalid_keywords = (
            Path('env/invalid_keyword.txt')
            .read_text()
            .split('\n')
        )[:-1]

        keyword_list = [
            i + " " + "\"" + suffix + "\""
            for i in list(set(predator_list))
        ]

        self.keyword_list = [
            i
            for i in keyword_list
            if i not in invalid_keywords
        ]

        self.geo = geo
        self.period = period
        self.suffix = suffix
        
        self.collector = NegativeKW_Collector(
            n_url,
            search_sleep,
            sentiment_model,
            extract_model
        )
        self.sentiment_model = sentiment_model
        self.extract_model = extract_model.split('/')[1]

    def setup(self, init_path: str = "gtab_config"):

        anchor_dir = Path(f"{init_path}/output/google_anchorbanks")
        anchor_file = "_".join((
            f"google_anchorbank_geo={self.geo}",
            f"timeframe={self.period[0]} {self.period[1]}.tsv"
        ))
        anchor_path = anchor_dir / anchor_file

        t = GTAB(dir_path=init_path)
        if not anchor_path.exists():
            t.set_options(pytrends_config={
                "geo": "",
                "time_frame": " ".join(self.period)
            })
            t.create_anchorbank()

        t.set_active_gtab(anchor_file)
        self.t = t

    def negative_search(self, predator: str):
        self.collector.setup(predator)
        output_path = (
            self.collector.output_dir 
            / 
            "_".join((
                self.extract_model,
                self.sentiment_model,
                str(self.collector.n_url),
                "keywords.json"
            ))
        )
        if output_path.exists():
            logger.info("negative search: keywords exists, fetch from the file")
            keywords = [
                i
                for i in orjson.loads(output_path.read_text())["keywords"]
            ]
        else:
            keywords = self.collector.fetch_keywords(output_path)

        return keywords


    def calibrate_instance(self, keyword: str):
        return (
            self.t
            .new_query(keyword)['max_ratio']
            .resample('M')
            .mean()
        )

    def calibrate_and_write(self, keyword: str, output_path: Path):
        status = 0
        try:
            logger.info(f"query: {keyword}")
            res = self.calibrate_instance(keyword)
        except ConnectionError as e:
            # self.t.set_options(
            #     conn_config={"proxies": ["https://"]}
            # )
            logger.warning(f"429 error: {keyword}")
            sys.exit()
        except:
            logger.info(f"fail to calibrate: {keyword}")
            status = -1

        if status == 0:
            with output_path.open('wb') as f:
                f.write(orjson.dumps(
                    {
                        "keyword": keyword,
                        "date":[i.date() for i in res.index],
                        "max_ratio": res.tolist()
                    },
                    option = orjson.OPT_INDENT_2
                ))
        return status

    def calibrate_batch(self, sleep: float = 5.):
        logger.remove()
        log_info = Path("log/gtab_info.log")
        log_warn = Path("log/gtab_warn.log")
        if log_info.exists(): log_info.unlink(missing_ok=True)
        if log_warn.exists(): log_warn.unlink(missing_ok=True)

        logger.add(log_info, level='INFO')
        logger.add(log_warn, level='WARNING')

        geo = "worldwide" if self.geo == "" else self.geo
        result_dir = Path(f"data/preprocess")

        self.t.set_options(
            gtab_config = {"sleep": sleep},
            # conn_config = {"proxies": ["https://"]}
        )
        for keyword in tqdm(self.keyword_list, position = 0):
            predator = keyword.split(' "')[0]
            output_dir = (
                result_dir
                /
                f"{predator}/gtab_result/{self.suffix}"
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{geo}_{self.period}.json"

            if not output_path.exists():
                status = self.calibrate_and_write(keyword, output_path)
                if status == -1:
                    negative_keywords = self.negative_search(predator)
                    find = False
                    for i in negative_keywords:
                        new_keyword = f'{predator} "{i}"'
                        status = self.calibrate_and_write(new_keyword, output_path)
                        if status == 0: 
                            find = True
                            break

                    if not find: logger.warning(f"fail have trend result: {predator}")
            else:
                logger.info(f"query result has alread exist: {keyword}")


@hydra.main(config_path="../../config", config_name="main", version_base=None)
def main(cfg: DictConfig):
    geo = "" if cfg.gtab.geo == "worldwide" else cfg.gtab.geo

    engine = TrendSearch(
        get_predator_list(cfg.gtab.keyword_path, cfg.gtab.sheet),
        cfg.gtab.suffix,
        geo,
        cfg.gtab.period,
        cfg.negative_search.n_url,
        cfg.negative_search.sleep,
        cfg.negative_search.sentiment_model,
        cfg.negative_search.extract_model
    )
    engine.setup(cfg.gtab.init_path)
    engine.calibrate_batch(cfg.gtab.sleep)


if __name__ == "__main__":
    main()
