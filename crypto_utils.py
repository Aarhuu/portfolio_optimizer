import re

import pandas as pd
import requests
import matplotlib.pyplot as plt
import seaborn as sns
import statsmodels.api as sm
from scipy import stats
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.metrics import mean_squared_error, accuracy_score
from sklearn.ensemble import RandomForestClassifier
import numpy as np

# from keras.models import Sequential
# #from keras.layers import LSTM
# from keras.layers import Dense
# from keras.layers import SimpleRNN
# from keras.layers import Dropout

class Visualizer():
    def __init__(self) -> None:
        pass

    def get_line_plot(self, data, title = "example plot"):
        columns = data.columns
        fig, ax = plt.subplots()
        for col in columns:
            ax.plot(data[col], label=col)
        ax.set_title(f"Series data from {data.index.values[0]} - {data.index.values[-1]}")
        plt.legend(loc="best")
        ax.tick_params(axis="x", rotation=45)
        ax.set_ylabel(title)
        plt.tight_layout()

    def get_hist(self, data):
        close_cols = [col for col in data if "Close" in col]  
        fig, axs = plt.subplots(ncols=1, nrows=len(close_cols))
        for i, col in enumerate(close_cols):
            sns.histplot(data[col], ax=axs[i], label=col)
            axs[0].set_title("Asd")
        plt.tight_layout()
    
    def get_box_plot(self, data):
        fig, ax = plt.subplots()
        sns.boxplot(data=data, ax=ax)
        ax.set_title(f"Box plot")
        plt.legend(loc="best")
        ax.tick_params(axis="x", rotation=90)
        ax.set_ylabel("Pair price")
        plt.tight_layout()

    def get_bar_counts(self, bar_df, freq="15min"):
        return bar_df.groupby(pd.Grouper(freq=freq)).first().iloc[:,0:].fillna(0).plot()
    
    def get_autocorr_plot(self, bar_df):
        close_cols = [col for col in bar_df if "Close" in col]
        fig, axs = plt.subplots(len(close_cols))
        for i, col in enumerate(close_cols):
            sm.graphics.tsa.plot_acf(bar_df[col], lags=100, ax=axs[i], title=f"Autocorr for {col}")
        
        plt.tight_layout()
     


class DataService():
    def __init__(self, api_url):
        self.api_url: str = api_url
        self.scaler = None

    def get_chain_data(self):
        chains = requests.get(self.api_url + "chains")
        chain_names = [chain["chain_name"] for chain in chains.json()]
        chain_slugs = [chain["chain_slug"] for chain in chains.json()]
        chain_id = [chain["chain_id"] for chain in chains.json()]
        chain_data = pd.DataFrame(data={
            "name" : chain_names,
            "slug": chain_slugs},
            index=chain_id)
        return chain_data

    def get_exchange_data(self, selected_chain: str, filter_zero_volume = "true"):
        api_extension = f"exchanges?chain_slug={selected_chain}&sort=usd_volume_30d&direction=desc&filter_zero_volume={filter_zero_volume}"
        exchanges = requests.get(self.api_url + api_extension)
        exc_names = [exc["exchange_slug"]for exc in exchanges.json()["exchanges"]]
        exc_vol = [exc["usd_volume_30d"]for exc in exchanges.json()["exchanges"]]
        exc_id = [exc["exchange_id"]for exc in exchanges.json()["exchanges"]]
        exchange_data = pd.DataFrame(data={
            "name" : exc_names,
            "volume": exc_vol},
            index=exc_id)
        return exchange_data
    
    def get_pairs_data(self, exc_slugs: list[str], chain_slugs: list[str], n_pairs: int, sort="volume_30d", filter="min_liquidity_1M"):
        exc_slug_string = ",".join(exc_slugs)
        chain_slug_string = ",".join(chain_slugs)
        api_extension = f"pairs?exchange_slugs={exc_slug_string}&chain_slugs={chain_slug_string}&page=0&page_size={n_pairs}&sort={sort}&direction=desc&filter={filter}&eligible_only=true&format=json"
        pairs = requests.get(self.api_url + api_extension)
        pair_id = [pair["pair_id"] for pair in pairs.json()["results"]]
        pair_slug = [pair["pair_slug"] for pair in pairs.json()["results"]]
        pair_exc = [pair["exchange_slug"] for pair in pairs.json()["results"]]
        pair_data = pd.DataFrame(data={
            "pair_slug" : pair_slug,
            "pair_exchange": pair_exc}, 
            index=pair_id)
        return pair_data
    
    def get_ohlcv_candles(self, pair_ids: list[int|str], start_time, end_time,  time_bucket="15m"):
        pair_ids_string = ",".join(map(str, pair_ids))
        api_extension = f"candles?pair_ids={pair_ids_string}&time_bucket={time_bucket}&candle_type=price&start={start_time}&end={end_time}"
        response = requests.get(self.api_url + api_extension)
        values = response.json()
        candle_dict = {}
        for key, value in values.items():
            ts = [val["ts"] for val in value]
            open = [val["o"] for val in value]
            high = [val["h"] for val in value]
            low = [val["l"] for val in value]
            close = [val["c"] for val in value]
            volume = [val["v"] for val in value]
            df = pd.DataFrame(data={"Open": open, "High": high, "Low": low, "Close": close, "Volume": volume}, index=pd.to_datetime(ts, format='%Y-%m-%dT%H:%M:%S'))
            candle_dict[key] = df
        return candle_dict
    
    def get_price_volume(self, data):

        pair_cols = [col for col in data.columns if "Close" in col]
        price_vol = pd.DataFrame()
        for col in pair_cols:
            pair_id = ''.join([i for i in col if not i.isalpha() and i != "_"])
            price_vol[pair_id+"_Price_Vol"] = data[pair_id + "_Close"] * data[pair_id + "_Volume"] 

        return price_vol
    
    def get_volume_bars(self, data, m):

        def get_volume_indxs(col):
            t = data[col]
            ts = 0
            idx = []
            for i, x in enumerate(t):
                ts += x
                if ts >= m:
                    idx.append(i)
                    ts = 0
                    continue
            return idx
        
        volume_df = pd.DataFrame()
        volume_columns = [col for col in data.columns if "Volume" in col]
        for column in volume_columns:
            indx = get_volume_indxs(column)
            colname = column.replace("Volume", "Close")
            volume_df[colname] = data.iloc[indx][colname].drop_duplicates()
        
        return volume_df
    
    def get_tick_bars(self, data, m):

        def get_tick_indxs(col):
            t = data[col]
            ts = 0
            idx = []
            for i, x in enumerate(t):
                ts += 1
                if ts > m:
                    idx.append(i)
                    ts = 0 
                    continue
            return idx

        tick_df = pd.DataFrame()
        price_columns = [col for col in data.columns if "Close" in col]
        for column in price_columns:
            indx = get_tick_indxs(column)
            tick_df[column] = data.iloc[indx][column].drop_duplicates()
        
        return tick_df
    
    def get_price_volume_bars(self, data, m):

        def get_token_indxs(col):
            t = data[col]
            ts = 0
            idx = []
            for i, x in enumerate(t):
                ts += x
                if ts >= m:
                    idx.append(i)
                    ts = 0
                    continue
            return idx

        token_df = pd.DataFrame()
        price_vol_columns = [col for col in data.columns if "Price_Vol" in col]
        for column in price_vol_columns:
            indx = get_token_indxs(column)
            colname = column.replace("Price_Vol", "Close")
            token_df[colname] = data.iloc[indx][colname].drop_duplicates()
        
        return token_df

    def create_master_candle_df(self, ohlcv_dict):
        columns = list(ohlcv_dict[list(ohlcv_dict.keys())[0]].columns)
        master_df = pd.DataFrame(data={}, index=ohlcv_dict[list(ohlcv_dict.keys())[0]].index.values)
        for key in ohlcv_dict.keys():
            for col in columns:
                master_df[str(key) + "_" + str(col)] = ohlcv_dict[key][col]
        
        if master_df.isnull().any().any():
            print("Candle data includes NaN values! Filling NaNs with either ffill or bfill")
            master_df = master_df.ffill().bfill()
        return master_df
    
    def get_close_prices(self, dataset):
        close_columns = [col for col in dataset.columns if "Close" in col]
        return dataset[close_columns]
    
    def get_log_returns(self, data):
        log_returns = pd.DataFrame()
        for col in data.columns:
            log_returns[col] = np.log(data[col]/data[col].shift(1))
        return log_returns
    
    def scale_data(self, data, scaler=MinMaxScaler(feature_range=(0,1))):
        self.scaler = scaler
        scaled = self.scaler.fit_transform(data)
        scaled = pd.DataFrame(data=scaled,
                              index=data.index,
                              columns = data.columns)
        return scaled
    
    def remove_outliers(self, data, threshold=3):
        return data[(np.abs(stats.zscore(data)) < threshold).all(axis=1)]
    
    def get_serial_correlation(self, data):
        corrs = pd.DataFrame(data={"autocorr": [0]*len(data.columns), "number_of_samples": [0]*len(data.columns)} ,index=data.columns)
        
        for col in data.columns:
           corrs.loc[col, "autocorr"] = pd.Series.autocorr(data[col])
           corrs.loc[col, "number_of_samples"] = data[col].dropna().shape[0]
        
        return corrs
    
    def get_adf_stats(self, data, orders = [0]):
        results = pd.DataFrame()

        for col in data.columns:
            for order in orders:
                diff = np.diff(data[col], order)
                res = sm.tsa.stattools.adfuller(diff)
                results[col + f"_Order_{order}"] = (res[0], res[1])

        return results.T
    
    def get_fracdiff_weights(self, d, lags):
        # return the weights from the series expansion of the differencing operator
        # for real orders d and up to lags coefficients
        w=[1]
        for k in range(1,lags):
            w.append(-w[-1]*((d-k+1))/k)
        w=np.array(w).reshape(-1,1) 
        return w
    
    def ts_differencing(self, series, orders, threshold, tau=1e-3):
        # return the time series resulting from (fractional) differencing
        # for real orders order up to lag_cutoff coefficients
        def cutoff_find(order, cutoff, start_lags):
            val=np.inf
            lags=start_lags
            while abs(val)>cutoff:
                w=self.get_fracdiff_weights(order, lags)
                val=w[-1]
                lags+=1
            return lags

        for o in orders:
            lag_cutoff = cutoff_find(o, tau, 1) #finding lag cutoff with tau
            weights = self.get_fracdiff_weights(o, lag_cutoff)
            res = 0
            for k in range(lag_cutoff):
                res += weights[k]*series.shift(k).fillna(0)
            if sm.tsa.stattools.adfuller(res[lag_cutoff:])[1] <= threshold:
                print(o)
                return res[lag_cutoff:] 
        raise Exception("No optimal differencing order found")
    
    def get_cusum_filter_indxs(self, data, h = None, span=100, devs = 2.5):
        e = pd.DataFrame(0, index=data.index,
                     columns=['CUSUM_Event'])
        s_pos = 0
        s_neg = 0
        r = data.pct_change()
        
        for idx in r.index:
            if h is None or len(r[:idx]) == 1:
                h_ = r[:idx].ewm(span=span).std().values[-1]*devs
            else: h_ = h
            s_pos = max(0, s_pos+r.loc[idx])
            s_neg = min(0, s_neg+r.loc[idx])        
            if s_neg < -h_:
                s_neg = 0
                e.loc[idx] = -1
            elif s_pos > h_:
                s_pos = 0
                e.loc[idx] = 1
        return e
    
    def get_daily_volatility(self, close, span=100):

        df0 = close.index.searchsorted(close.index-pd.Timedelta(days=1))

        df0 = df0[df0>0]

        df0 = pd.Series(close.index[df0-1],
                    index=close.index[close.shape[0]-df0.shape[0]:])

        df0 = close.loc[df0.index]/close.loc[df0.values].values-1 # daily rets

        df0 = df0.ewm(span=span).std()
        return df0

    def get_X_Y(self, dataset, target_columns):
        data_array = dataset.to_numpy()
        X = np.delete(data_array, range(-len(target_columns), 0), 1)
        Y = data_array[:, range(-len(target_columns), 0)]
        return X, Y

    def add_lookback_columns(self, dataset, look_back=1):
        shifted = dataset.shift(look_back)
        colnames = {col: col + f"_shifted_{look_back}" for col in shifted.columns}
        shifted = shifted.rename(columns=colnames).bfill()
        return shifted

    def add_signal_column(self, dataset):
        return [1 if x > 0 else 0 for x in dataset.diff().bfill()]
        
    def create_simple_rnn_regressor(self, dense_units, hidden_units, input_shape, activations):
        # initializing the RNN
        regressor = Sequential()
        
        # adding RNN layers and dropout regularization
        regressor.add(SimpleRNN(units = hidden_units, 
                                activation = activations[0],
                                return_sequences = True,
                                input_shape = input_shape))
        regressor.add(Dropout(0.2))
        
        regressor.add(SimpleRNN(units = hidden_units, 
                                activation = activations[0],
                                return_sequences = True))
        
        regressor.add(SimpleRNN(units = hidden_units, 
                                activation = activations[0],
                                return_sequences = True))
        
        regressor.add(SimpleRNN(units = hidden_units))
        
        # adding the output layer
        regressor.add(Dense(units = dense_units, activation=activations[1]))
        
        # compiling RNN
        regressor.compile(optimizer = "adam", 
                        loss = "mean_squared_error")
        
        return regressor
    

if __name__ == "__main__":
    api_url = "https://tradingstrategy.ai/api/"
    data_service = DataService(api_url=api_url)
    chain_data = data_service.get_chain_data()
    selected_chain = chain_data.iloc[0]["slug"]
    exchange_data = data_service.get_exchange_data(selected_chain=selected_chain)

    n_exchange = 3
    n_pairs = 3
    time_bucket = "1m"

    pairs_data = data_service.get_pairs_data(
        exc_slugs=exchange_data.iloc[0:n_exchange]["name"],
        chain_slugs=[selected_chain],
        n_pairs=n_pairs)
    start_time = "2024-01-01"
    end_time = "2024-01-15"
    candle_dict = data_service.get_ohlcv_candles(list(pairs_data.index.values), start_time, end_time, time_bucket=time_bucket)
    master_df = data_service.create_master_candle_df(candle_dict)
    master_df = pd.concat([master_df, data_service.get_price_volume(master_df)], axis=1)
    close_prices = data_service.get_close_prices(master_df)
    p_v_bars = data_service.get_price_volume_bars(master_df, m=1000000)
    p_v_bars_scaled = data_service.scale_data(p_v_bars)
    close_price_means = [close_prices[col].sum() for col in close_prices.columns]
    vol_bar_freq = np.mean(close_price_means)/close_prices.shape[0]
    vol_bars = data_service.get_volume_bars(master_df, m=vol_bar_freq).ffill().bfill()
    vol_bars_scaled = data_service.scale_data(vol_bars)
    p_v_bars_log = data_service.get_log_returns(p_v_bars).fillna(method="bfill")
    #p_v_bars_log = p_v_bars_log.fillna(method="bfill")
    vol_bars_log = data_service.get_log_returns(vol_bars).fillna(method="bfill")
    #vol_bars_log = vol_bars_log.fillna(method="bfill")
    close_log = data_service.get_log_returns(close_prices).fillna(method="bfill")
    #close_log = close_log.fillna(method="bfill")
    # print(data_service.get_serial_correlation(p_v_bars_log))
    # print(data_service.get_serial_correlation(vol_bars_log))
    # print(data_service.get_serial_correlation(close_log))
    # print(data_service.get_adf_stats(close_prices, orders = [0, 1, 2]))
    print(data_service.get_adf_stats(vol_bars_log))
    diffed_volume = data_service.ts_differencing(vol_bars['1_Close'], np.divide(range(0, 100), 100), 0.01).bfill()
    cusum = data_service.get_cusum_filter_indxs(diffed_volume, devs=2.5)
    daily_vol = data_service.get_daily_volatility(diffed_volume)
    daily_vol.plot()

    plt.show()
    # price_vol_df = data_service.get_token_value_bars(master_df, m=100)
    # vol_bar_df = data_service.get_volume_bars(master_df, m=100).dropna()
    # tick_bar_df = data_service.get_tick_bars(master_df, m=100)
    # scaled_vols = data_service.scale_data(vol_bar_df)
    # scaled_ticks = data_service.scale_data(tick_bar_df)
    #log_returns = data_service.get_log_returns(vol_bar_df)
    #serial_autocorr = data_service.get_serial_correlation(log_returns)

    # vis = Visualizer()

    # log_returns = data_service.get_log_returns(close_prices)
    # scaled_closes = data_service.scale_data(close_prices)


#1_Close  3366033_Close     239_Close
