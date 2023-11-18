from loguru import logger
import numpy as np
import orjson
import pandas as pd
from pathlib import Path
from time import strptime


def get_predator_list(path: str = "data/raw/victim_list_01252023.xlsx", 
                      sheet: str = "Ri",
                      col: str = "predator"
                      ):
    file_name = path.split('/')[-1].split('.')[0]
    output_path = Path(f"data/raw/{file_name}_{sheet}.txt")

    if output_path.exists():
        logger.info(f"fetch list of {col} from existed files")
        res = [
            i
            for i in output_path.read_text().split('\n')
            if i != ''
        ]
    else:
        _res = (
            pd
            .read_excel(path, sheet_name=sheet)[col]
            .to_list()
        )
        res = list(set(_res))

        logger.info(f"save the list of {col}")
        with output_path.open('w') as f:
            for i in res:
                f.write(i + "\n")

    return res

def merge_all_gtab_res(input_dir: str = 'data/gtab_res/predator/original',
                       raw_data_path: str = 'data/raw/victim_list_01252023.xlsx',
                       output_data_path: str = 'data/processed/victim_list_01252023.xlsx',
                       adjust_method: str = 'mean',
                       write: bool = True
                      ) -> None:
    input_dir_ = Path(input_dir)
    input_paths = list(input_dir_.glob('*/*.json'))
    _col_name = [
        '_'.join(i.split('-')[:-1] )
        for i in orjson.loads(input_paths[0].read_text()).get('date')
    ]
    col_name_freq = {}
    for i in _col_name:
        if i not in col_name_freq:
            col_name_freq[i] = 1
        else:
            col_name_freq[i] += 1
    _res = [orjson.loads(i.read_text()) for i in input_paths]
    res = {
        i.get('keyword'): i.get('max_ratio') 
        for i in _res
    }
    target = 'predator' if input_dir.split('/')[2] == 'predator' else 'victim'
    sheet = 'Ri' if target == 'predator' else 'Rj'

    ri = pd.read_excel(raw_data_path, sheet_name=sheet)
    target_names = ri.get(target).to_list()
    data = []
    match adjust_method:
        case 'mean':
            for idx, i in enumerate(target_names):
                beg = 0
                end = 0
                data_i = [i, idx+1]
                for j in col_name_freq.values():
                    end += j
                    try:
                        data_i.append(np.mean(res.get(i)[beg:end]))
                    except:
                        data_i.append(None)
                    beg = end
                data.append(data_i)
        case 'sum':
            for idx, i in enumerate(target_names):
                beg = 0
                end = 0
                data_i = [i, idx+1]
                for j in col_name_freq.values():
                    end += j
                    try:
                        data_i.append(np.sum(res.get(i)[beg:end]))
                    except:
                        data_i.append(None)
                    beg = end
                data.append(data_i)


    df = pd.DataFrame(data, columns = [target, f'{target}_id'] + list(col_name_freq.keys()))
    if write:
        logger.info(f"add(replace) sheet: new_{sheet}_{adjust_method}")
        with pd.ExcelWriter(output_data_path,
                            mode='a',
                            if_sheet_exists = 'replace'
                            ) as writer:
            df.to_excel(writer, sheet_name = f'new_{sheet}_{adjust_method}', index = False)

    return df

def adjust_ait(input_data_path = 'data/processed/victim_list_10302023.xlsx',
               predator_victim_sheet = '名單',
               ait_csv_path = 'data/raw/ait.csv',
               write = True,
               sum = False
              ):
    df_date = pd.read_excel(input_data_path, sheet_name = predator_victim_sheet)
    victim2date = {
        df_date.iloc[i]['victim']: df_date.iloc[i]['time']
        for i in range(len(df_date))
    }

    predator2victim = {}
    for i in range(len(df_date)):
        predator = df_date.iloc[i]['predator']
        victim = df_date.iloc[i]['victim']
        if predator not in predator2victim:
            predator2victim[predator] = [victim]
        else:
            predator2victim[predator].append(victim)

    victim2predator = {
        df_date.iloc[i]['victim']: df_date.iloc[i]['predator'] 
        for i in range(len(df_date))
    }

    victim2friend = {}
    for victim in victim2predator.keys():
        predator = victim2predator[victim]
        possible_friends = predator2victim[predator]
        victim2friend[victim] = []
        for i in possible_friends:
            if i != victim: victim2friend[victim].append(i)

    df_a = pd.read_csv(ait_csv_path)
    interval = [
        pd.to_datetime(f'20{i[3:5]}-{strptime(i[:3],"%b").tm_mon}', format = '%Y-%m') 
        for i in df_a.columns 
        if i not in ['predator', 'predator_id', 'victim', 'victim_id ']
    ]
    victim2id = {
        df_a.iloc[i]['victim']: df_a.iloc[i]['victim_id '] - 1
        for i in range(len(df_a))
    }

    victim2friend_id = {
        victim: list(map(lambda x: victim2id[x], victim2friend[victim]))
        for victim in victim2friend.keys()
    }

    s = np.zeros((len(victim2date.keys()), len(interval)))
    for idx_i, victim in enumerate(victim2date.keys()):
        issue_date = victim2date[victim]
        for idx_j, date in enumerate(interval):
            if date > issue_date:
                s[idx_i][idx_j] = 1
            elif date.year == issue_date.year and date.month == issue_date.month:
                s[idx_i][idx_j] = 1

    s_adjust = np.zeros((len(victim2date.keys()), len(interval)))
    for idx_i, victim in enumerate(victim2date.keys()):
        if len(victim2friend_id[victim]) != 0:
            for id in victim2friend_id[victim]:
                s_adjust[idx_i] += s[id]

    new_sheet_name = 'adjust_ait'
    if sum:
        new_sheet_name = 'sum_adjust_ait'
        logger.info(f'new sheet: {new_sheet_name}')

        victim2section = {
            df_date.iloc[i]['victim']: df_date.iloc[i]['section']
            for i in range(len(df_date))
        }
        section2victim_id = {}
        for i in range(len(df_date)):
            section = df_date.iloc[i]['section']
            victim = df_date.iloc[i]['victim']
            if section not in section2victim_id:
                section2victim_id[section] = [victim2id[victim]]
            else:
                section2victim_id[section].append(victim2id[victim])

        victim2section_friend_id = {}
        for victim in victim2predator.keys():
            section = victim2section[victim]
            possible_friends = section2victim_id[section]

            victim2section_friend_id[victim] = []
            for i in possible_friends:
                if i not in victim2friend_id[victim] and i != victim2id[victim]:
                    victim2section_friend_id[victim].append(i)

        for idx_i, victim in enumerate(victim2date.keys()):
            if len(victim2section_friend_id[victim]) != 0:
                for id in victim2section_friend_id[victim]:
                        s_adjust[idx_i] += s[id]

    df_a_adjust = pd.DataFrame({
        'predator': df_a['predator'],
        'predaotr_id': df_a['predator_id'],
        'victim': df_a['victim'],
        'victim_id': df_a['victim_id ']
    })


    for idx, i in enumerate(interval):
        df_a_adjust[i] = [i[idx] for i in s_adjust]

    if write:
        with pd.ExcelWriter(input_data_path,
                            mode='a',
                            if_sheet_exists = 'replace'
                            ) as writer:
            df_a_adjust.to_excel(writer, sheet_name = new_sheet_name, index = False)

    return df_a_adjust


def create_ri_for_regression(input_path: str = 'data/processed/victim_list_10302023.xlsx',
                             predator_victim_info: str = 'S', 
                             ri:str = 'new_Ri_sum_smooth',
                             new_sheet: str = 'new_Ri_for_regression',
                             write = True
                            ):
    logger.info(input_path)
    df_predator_victim = pd.read_excel(
        input_path, 
        sheet_name = predator_victim_info
    )
    df_ri =  pd.read_excel(input_path, sheet_name = ri)

    df = pd.DataFrame({
        'predator': df_predator_victim['predator'],
        'predaotr_id': df_predator_victim['predator_id'],
        'victim': df_predator_victim['victim'],
        'victim_id': df_predator_victim['victim_id ']
    })

    predator2freq = {}
    for i in range(len(df)):
        predator = df.iloc[i]['predator']
        if  predator not in predator2freq:
            predator2freq[predator] = [0]
        else:
            predator2freq[predator][0] += 1

    target_cols = df_ri.columns.drop(['predator', 'predator_id'])
    for col in target_cols:
        predaotr2ri = {
            df_ri.iloc[i]['predator']: df_ri.iloc[i][col]
            for i in range(len(df_ri))
        }
        df[col] = [
            predaotr2ri[predator]
            for predator in df['predator']
        ]
        
    if write:
        with pd.ExcelWriter(input_path,
                            mode='a',
                            if_sheet_exists = 'replace'
                            ) as writer:
            df.to_excel(writer, sheet_name = new_sheet, index = False)

    return df
