#core/ai_predictor.py
"""
ماژول هوش مصنوعی برای پیش‌بینی و بهینه‌سازی سرعت
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
from dataclasses import dataclass, field, asdict
import pickle
import hashlib
from collections import defaultdict, deque
import statistics

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import Dataset, DataLoader
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("PyTorch not available, using fallback methods")

try:
    import tensorflow as tf
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False

from config.settings import config_manager

logger = logging.getLogger(__name__)

@dataclass
class PredictionFeatures:
    """ویژگی‌های ورودی برای پیش‌بینی"""
    file_size: int
    time_of_day: int  # ساعت 0-23
    day_of_week: int  # 0-6
    network_type: str  # wifi, mobile, ethernet, satellite
    server_location: str
    historical_speed: float = 0.0
    latency: float = 0.0
    packet_loss: float = 0.0
    bandwidth: float = 0.0
    user_id: Optional[str] = None
    file_type: Optional[str] = None
    
    def to_array(self) -> np.ndarray:
        """تبدیل به آرایه numpy"""
        # تبدیل مقادیر به فرم عددی
        features = [
            np.log1p(self.file_size),
            self.time_of_day / 24.0,
            self.day_of_week / 7.0,
            self._encode_network_type(self.network_type),
            self._encode_location(self.server_location),
            np.log1p(self.historical_speed) if self.historical_speed > 0 else 0,
            np.log1p(self.latency) if self.latency > 0 else 0,
            self.packet_loss,
            np.log1p(self.bandwidth) if self.bandwidth > 0 else 0,
        ]
        
        # اضافه کردن one-hot encoding برای file_type
        if self.file_type:
            file_types = ['video', 'audio', 'image', 'document', 'archive', 'other']
            encoding = [1 if self.file_type == ft else 0 for ft in file_types]
            features.extend(encoding)
        
        return np.array(features, dtype=np.float32)
    
    def _encode_network_type(self, network_type: str) -> float:
        """کدگذاری نوع شبکه"""
        encoding = {
            'ethernet': 1.0,
            'wifi': 0.8,
            'mobile_5g': 0.6,
            'mobile_4g': 0.4,
            'mobile_3g': 0.2,
            'satellite': 0.1,
            'unknown': 0.5
        }
        return encoding.get(network_type.lower(), 0.5)
    
    def _encode_location(self, location: str) -> float:
        """کدگذاری موقعیت جغرافیایی"""
        # اینجا می‌توان از geolocation استفاده کرد
        # فعلاً یک نگاشت ساده
        if not location:
            return 0.5
        
        # تقسیم موقعیت به مناطق
        regions = {
            'us': 0.9, 'eu': 0.8, 'asia': 0.7,
            'middle_east': 0.6, 'africa': 0.5,
            'local': 1.0, 'cdn': 0.95
        }
        
        for region, value in regions.items():
            if region in location.lower():
                return value
        
        return 0.5

@dataclass
class PredictionResult:
    """نتیجه پیش‌بینی"""
    predicted_speed_mbps: float
    confidence: float
    optimal_strategy: str
    recommended_chunk_size: int
    recommended_connections: int
    estimated_time: float
    features_used: List[str]
    model_version: str
    
    def to_dict(self) -> Dict:
        return asdict(self)

class SpeedPredictionModel:
    """مدل پایه پیش‌بینی سرعت"""
    
    def __init__(self):
        self.model_version = "1.0.0"
        self.training_data: List[Tuple[PredictionFeatures, float]] = []
        self.model = None
        self.scaler = None
        self.last_trained = None
        self.training_threshold = 100  # حداقل داده برای آموزش
        
    async def predict(self, features: PredictionFeatures) -> PredictionResult:
        """پیش‌بینی سرعت"""
        raise NotImplementedError
    
    async def update(self, features: PredictionFeatures, actual_speed: float):
        """به‌روزرسانی مدل با داده جدید"""
        self.training_data.append((features, actual_speed))
        
        # آموزش مجدد اگر داده کافی باشد
        if len(self.training_data) >= self.training_threshold:
            await self.retrain()
    
    async def retrain(self):
        """آموزش مجدد مدل"""
        raise NotImplementedError
    
    def save(self, path: Path):
        """ذخیره مدل"""
        raise NotImplementedError
    
    def load(self, path: Path):
        """بارگذاری مدل"""
        raise NotImplementedError

class NeuralNetworkPredictor(SpeedPredictionModel):
    """پیش‌بین با شبکه عصبی"""
    
    def __init__(self):
        super().__init__()
        self.model_version = "2.0.0"
        
        if TORCH_AVAILABLE:
            self._init_neural_network()
        elif TENSORFLOW_AVAILABLE:
            self._init_tensorflow_model()
        else:
            self._init_fallback_model()
    
    def _init_neural_network(self):
        """ایجاد شبکه عصبی با PyTorch"""
        class SpeedNet(nn.Module):
            def __init__(self, input_size: int, hidden_size: int = 128):
                super(SpeedNet, self).__init__()
                self.network = nn.Sequential(
                    nn.Linear(input_size, hidden_size),
                    nn.ReLU(),
                    nn.Dropout(0.2),
                    nn.Linear(hidden_size, hidden_size // 2),
                    nn.ReLU(),
                    nn.Dropout(0.2),
                    nn.Linear(hidden_size // 2, 64),
                    nn.ReLU(),
                    nn.Linear(64, 32),
                    nn.ReLU(),
                    nn.Linear(32, 1),
                    nn.Sigmoid()  # خروجی بین 0-1 (نرمالایز شده)
                )
            
            def forward(self, x):
                return self.network(x)
        
        self.model = SpeedNet(input_size=16)  # 16 ویژگی
        self.optimizer = optim.Adam(self.model.parameters(), lr=0.001)
        self.criterion = nn.MSELoss()
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model.to(self.device)
        
        logger.info(f"Neural network initialized on {self.device}")
    
    def _init_tensorflow_model(self):
        """ایجاد مدل با TensorFlow"""
        try:
            self.model = tf.keras.Sequential([
                tf.keras.layers.Dense(128, activation='relu', input_shape=(16,)),
                tf.keras.layers.Dropout(0.2),
                tf.keras.layers.Dense(64, activation='relu'),
                tf.keras.layers.Dropout(0.2),
                tf.keras.layers.Dense(32, activation='relu'),
                tf.keras.layers.Dense(1, activation='sigmoid')
            ])
            
            self.model.compile(
                optimizer='adam',
                loss='mse',
                metrics=['mae']
            )
            
            logger.info("TensorFlow model initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize TensorFlow model: {e}")
            self._init_fallback_model()
    
    def _init_fallback_model(self):
        """مدل ساده جایگزین"""
        logger.info("Using fallback prediction model")
        self.model = "linear_regression"
        # استفاده از رگرسیون خطی ساده
    
    async def predict(self, features: PredictionFeatures) -> PredictionResult:
        """پیش‌بینی با شبکه عصبی"""
        try:
            # استخراج ویژگی‌ها
            feature_array = features.to_array()
            
            if TORCH_AVAILABLE and isinstance(self.model, nn.Module):
                # پیش‌بینی با PyTorch
                self.model.eval()
                with torch.no_grad():
                    input_tensor = torch.FloatTensor(feature_array).unsqueeze(0).to(self.device)
                    prediction = self.model(input_tensor).item()
            
            elif TENSORFLOW_AVAILABLE and isinstance(self.model, tf.keras.Model):
                # پیش‌بینی با TensorFlow
                prediction = self.model.predict(feature_array.reshape(1, -1), verbose=0)[0][0]
            
            else:
                # استفاده از مدل ساده
                prediction = self._simple_prediction(features)
            
            # تبدیل به سرعت واقعی (Mbps)
            # نرمالایز کردن بر اساس محدوده‌های واقعی
            max_speed = 1000  # Mbps - حداکثر سرعت منطقی
            predicted_speed = prediction * max_speed
            
            # محاسبه confidence
            confidence = self._calculate_confidence(features, predicted_speed)
            
            # تولید توصیه‌ها
            recommendations = self._generate_recommendations(features, predicted_speed)
            
            return PredictionResult(
                predicted_speed_mbps=predicted_speed,
                confidence=confidence,
                optimal_strategy=recommendations['strategy'],
                recommended_chunk_size=recommendations['chunk_size'],
                recommended_connections=recommendations['connections'],
                estimated_time=self._estimate_time(features.file_size, predicted_speed),
                features_used=[str(f) for f in feature_array],
                model_version=self.model_version
            )
            
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            # بازگشت به مقادیر پیش‌فرض
            return self._default_prediction(features)
    
    def _simple_prediction(self, features: PredictionFeatures) -> float:
        """پیش‌بینی ساده با رگرسیون خطی"""
        # وزن‌های تجربی
        weights = {
            'file_size': -0.1,  # فایل‌های بزرگتر معمولاً سرعت متوسط کمتری دارند
            'time_of_day': -0.05,  # شب‌ها ممکن است سریع‌تر باشد
            'network_type': 0.3,   # نوع شبکه مهم‌ترین عامل
            'latency': -0.2,       # تاخیر بالا = سرعت پایین
            'bandwidth': 0.4       # پهنای باند مستقیم روی سرعت اثر دارد
        }
        
        score = 0.5  # مقدار پایه
        
        # اعمال وزن‌ها
        score += weights['file_size'] * (np.log1p(features.file_size) / 20)
        score += weights['time_of_day'] * (features.time_of_day / 24 - 0.5)
        score += weights['network_type'] * features._encode_network_type(features.network_type)
        score += weights['latency'] * max(0, 1 - min(features.latency, 500) / 500)
        
        if features.bandwidth > 0:
            score += weights['bandwidth'] * (min(features.bandwidth, 1000) / 1000)
        
        # محدود کردن بین 0 و 1
        return max(0.0, min(1.0, score))
    
    def _calculate_confidence(self, features: PredictionFeatures, predicted_speed: float) -> float:
        """محاسبه confidence پیش‌بینی"""
        confidence = 0.7  # مقدار پایه
        
        # افزایش confidence بر اساس داده‌های تاریخی مشابه
        similar_data = self._find_similar_data(features)
        if similar_data:
            avg_accuracy = np.mean([abs(s[1] - predicted_speed) / max(s[1], 1) 
                                   for s in similar_data])
            confidence *= (1 - min(avg_accuracy, 0.5))
        
        # کاهش confidence برای داده‌های outlier
        if features.file_size > 10 * 1024 * 1024 * 1024:  # بیش از 10GB
            confidence *= 0.8
        
        if features.latency > 500:  # تاخیر بسیار بالا
            confidence *= 0.7
        
        return max(0.1, min(1.0, confidence))
    
    def _find_similar_data(self, features: PredictionFeatures, max_results: int = 10) -> List[Tuple]:
        """یافتن داده‌های مشابه تاریخی"""
        if not self.training_data:
            return []
        
        similarities = []
        feature_array = features.to_array()
        
        for train_features, actual_speed in self.training_data[-100:]:  # آخرین 100 رکورد
            train_array = train_features.to_array()
            
            # محاسبه شباهت با فاصله اقلیدسی
            distance = np.linalg.norm(feature_array - train_array)
            similarity = 1 / (1 + distance)
            
            similarities.append((similarity, (train_features, actual_speed)))
        
        # مرتب‌سازی بر اساس شباهت
        similarities.sort(reverse=True, key=lambda x: x[0])
        
        return [data for _, data in similarities[:max_results]]
    
    def _generate_recommendations(self, features: PredictionFeatures, 
                                predicted_speed: float) -> Dict[str, Any]:
        """تولید توصیه‌های بهینه‌سازی"""
        
        # تعیین استراتژی
        if predicted_speed < 5:  # کمتر از 5 Mbps
            strategy = "single"
            connections = 1
            chunk_size = 512 * 1024  # 512KB
        
        elif predicted_speed < 20:  # 5-20 Mbps
            strategy = "multi_connection"
            connections = min(4, max(2, int(predicted_speed / 5)))
            chunk_size = 1024 * 1024  # 1MB
        
        elif predicted_speed < 100:  # 20-100 Mbps
            strategy = "adaptive"
            connections = min(8, max(4, int(predicted_speed / 10)))
            chunk_size = 2 * 1024 * 1024  # 2MB
        
        else:  # بیشتر از 100 Mbps
            strategy = "aggressive"
            connections = min(16, max(8, int(predicted_speed / 20)))
            chunk_size = 5 * 1024 * 1024  # 5MB
        
        # تنظیم بر اساس نوع شبکه
        if features.network_type in ['mobile_3g', 'satellite']:
            connections = max(1, connections // 2)
            chunk_size = max(256 * 1024, chunk_size // 2)
        
        # تنظیم بر اساس تاخیر
        if features.latency > 200:
            connections = max(1, connections // 2)
        
        return {
            'strategy': strategy,
            'connections': connections,
            'chunk_size': chunk_size,
            'compression': predicted_speed < 10,  # فشرده‌سازی برای سرعت‌های پایین
            'resume': features.file_size > 10 * 1024 * 1024  # فایل‌های بزرگ
        }
    
    def _estimate_time(self, file_size: int, speed_mbps: float) -> float:
        """تخمین زمان انتقال"""
        if speed_mbps <= 0:
            return 0
        
        size_mb = file_size / (1024 * 1024)
        return size_mb / speed_mbps  # ثانیه
    
    def _default_prediction(self, features: PredictionFeatures) -> PredictionResult:
        """پیش‌بینی پیش‌فرض در صورت خطا"""
        default_speed = 10.0  # Mbps
        
        return PredictionResult(
            predicted_speed_mbps=default_speed,
            confidence=0.3,
            optimal_strategy="adaptive",
            recommended_chunk_size=1024 * 1024,
            recommended_connections=4,
            estimated_time=self._estimate_time(features.file_size, default_speed),
            features_used=["default"],
            model_version=self.model_version + "_fallback"
        )
    
    async def retrain(self):
        """آموزش مجدد شبکه عصبی"""
        if len(self.training_data) < self.training_threshold:
            logger.info("Not enough data for retraining")
            return
        
        logger.info(f"Retraining model with {len(self.training_data)} samples")
        
        try:
            # آماده‌سازی داده
            X = []
            y = []
            
            for features, actual_speed in self.training_data:
                X.append(features.to_array())
                # نرمالایز کردن سرعت واقعی
                max_speed = 1000
                y.append(min(actual_speed / max_speed, 1.0))
            
            X = np.array(X)
            y = np.array(y)
            
            if TORCH_AVAILABLE and isinstance(self.model, nn.Module):
                # آموزش با PyTorch
                dataset = TensorDataset(torch.FloatTensor(X), torch.FloatTensor(y))
                dataloader = DataLoader(dataset, batch_size=32, shuffle=True)
                
                self.model.train()
                for epoch in range(10):
                    epoch_loss = 0
                    for batch_X, batch_y in dataloader:
                        batch_X, batch_y = batch_X.to(self.device), batch_y.to(self.device)
                        
                        self.optimizer.zero_grad()
                        predictions = self.model(batch_X)
                        loss = self.criterion(predictions.squeeze(), batch_y)
                        loss.backward()
                        self.optimizer.step()
                        
                        epoch_loss += loss.item()
                    
                    logger.debug(f"Epoch {epoch+1}, Loss: {epoch_loss/len(dataloader):.4f}")
                
                self.model.eval()
            
            elif TENSORFLOW_AVAILABLE and isinstance(self.model, tf.keras.Model):
                # آموزش با TensorFlow
                self.model.fit(
                    X, y,
                    epochs=10,
                    batch_size=32,
                    validation_split=0.2,
                    verbose=0
                )
            
            self.last_trained = time.time()
            self.model_version = f"{self.model_version.split('.')[0]}.{int(time.time())}"
            
            logger.info(f"Model retrained successfully. New version: {self.model_version}")
            
            # ذخیره مدل
            await self._save_model()
            
        except Exception as e:
            logger.error(f"Model retraining failed: {e}")
    
    async def _save_model(self):
        """ذخیره مدل آموزش دیده"""
        try:
            model_dir = Path("models")
            model_dir.mkdir(exist_ok=True)
            
            if TORCH_AVAILABLE and isinstance(self.model, nn.Module):
                model_path = model_dir / f"speed_predictor_{self.model_version}.pth"
                torch.save({
                    'model_state_dict': self.model.state_dict(),
                    'optimizer_state_dict': self.optimizer.state_dict(),
                    'training_data': self.training_data,
                    'version': self.model_version
                }, model_path)
            
            elif TENSORFLOW_AVAILABLE and isinstance(self.model, tf.keras.Model):
                model_path = model_dir / f"speed_predictor_{self.model_version}.h5"
                self.model.save(model_path)
            
            else:
                # ذخیره داده‌های آموزش
                data_path = model_dir / f"training_data_{self.model_version}.pkl"
                with open(data_path, 'wb') as f:
                    pickle.dump(self.training_data, f)
            
            logger.info(f"Model saved to {model_dir}")
            
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
    
    async def load_model(self, model_path: Path):
        """بارگذاری مدل ذخیره شده"""
        try:
            if TORCH_AVAILABLE and model_path.suffix == '.pth':
                checkpoint = torch.load(model_path, map_location=self.device)
                self.model.load_state_dict(checkpoint['model_state_dict'])
                self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
                self.training_data = checkpoint['training_data']
                self.model_version = checkpoint['version']
            
            elif TENSORFLOW_AVAILABLE and model_path.suffix == '.h5':
                self.model = tf.keras.models.load_model(model_path)
            
            elif model_path.suffix == '.pkl':
                with open(model_path, 'rb') as f:
                    self.training_data = pickle.load(f)
            
            self.last_trained = time.time()
            logger.info(f"Model loaded from {model_path}")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")

class AISpeedPredictor:
    """مدیر اصلی پیش‌بینی هوش مصنوعی"""
    
    def __init__(self):
        self.config = config_manager.settings
        self.models: Dict[str, SpeedPredictionModel] = {}
        self.user_profiles: Dict[str, Dict] = defaultdict(dict)
        self.pattern_detector = PatternDetector()
        self.anomaly_detector = AnomalyDetector()
        
        # بارگذاری مدل‌ها
        self._load_models()
        
        logger.info(f"AISpeedPredictor initialized with {len(self.models)} models")
    
    def _load_models(self):
        """بارگذاری مدل‌های مختلف"""
        # مدل عمومی
        self.models['general'] = NeuralNetworkPredictor()
        
        # مدل‌های تخصصی
        self.models['video'] = NeuralNetworkPredictor()
        self.models['document'] = NeuralNetworkPredictor()
        self.models['archive'] = NeuralNetworkPredictor()
        
        # مدل کاربر
        self.models['user_specific'] = NeuralNetworkPredictor()
    
    async def predict_speed(
        self,
        file_size: int,
        user_id: Optional[str] = None,
        time_of_day: Optional[int] = None,
        network_type: Optional[str] = None,
        server_location: str = "unknown",
        file_type: Optional[str] = None
    ) -> PredictionResult:
        """پیش‌بینی سرعت انتقال"""
        
        # تنظیم مقادیر پیش‌فرض
        if time_of_day is None:
            time_of_day = datetime.now().hour
        
        if network_type is None:
            network_type = "unknown"
        
        # ایجاد ویژگی‌ها
        features = PredictionFeatures(
            file_size=file_size,
            time_of_day=time_of_day,
            day_of_week=datetime.now().weekday(),
            network_type=network_type,
            server_location=server_location,
            user_id=user_id,
            file_type=file_type
        )
        
        # انتخاب مدل مناسب
        model_key = self._select_model(features)
        model = self.models[model_key]
        
        # پیش‌بینی
        result = await model.predict(features)
        
        # اعمال تنظیمات کاربر
        if user_id and user_id in self.user_profiles:
            result = self._apply_user_profile(result, user_id)
        
        # تشخیص الگوهای زمانی
        time_pattern = await self.pattern_detector.detect_time_pattern(user_id)
        if time_pattern:
            result.predicted_speed_mbps *= time_pattern.get('speed_factor', 1.0)
        
        # بررسی anomalies
        if await self.anomaly_detector.is_anomaly(features, result.predicted_speed_mbps):
            result.confidence *= 0.5
            logger.warning(f"Anomaly detected for prediction: {result}")
        
        return result
    
    def _select_model(self, features: PredictionFeatures) -> str:
        """انتخاب مدل مناسب برای پیش‌بینی"""
        
        if features.user_id and features.user_id in self.user_profiles:
            if self.user_profiles[features.user_id].get('has_enough_data', False):
                return 'user_specific'
        
        if features.file_type:
            if features.file_type in self.models:
                return features.file_type
        
        return 'general'
    
    def _apply_user_profile(self, result: PredictionResult, user_id: str) -> PredictionResult:
        """اعمال پروفایل کاربر روی پیش‌بینی"""
        profile = self.user_profiles[user_id]
        
        # تنظیم بر اساس میانگین سرعت کاربر
        if 'avg_speed' in profile:
            user_factor = result.predicted_speed_mbps / max(profile['avg_speed'], 1)
            if 0.5 < user_factor < 2.0:  # اگر در محدوده منطقی باشد
                result.predicted_speed_mbps = profile['avg_speed']
                result.confidence *= 1.1
        
        return result
    
    async def update_model(
        self,
        user_id: str,
        actual_speed: float,
        file_size: int,
        network_metrics: Optional[Dict] = None
    ):
        """به‌روزرسانی مدل با داده واقعی"""
        
        # ایجاد ویژگی‌ها
        features = PredictionFeatures(
            file_size=file_size,
            time_of_day=datetime.now().hour,
            day_of_week=datetime.now().weekday(),
            network_type=network_metrics.get('type', 'unknown') if network_metrics else 'unknown',
            server_location='local',  # فرض می‌کنیم انتقال محلی است
            user_id=user_id,
            historical_speed=actual_speed
        )
        
        if network_metrics:
            features.latency = network_metrics.get('latency', 0)
            features.packet_loss = network_metrics.get('packet_loss', 0)
            features.bandwidth = network_metrics.get('bandwidth', 0)
        
        # به‌روزرسانی مدل عمومی
        await self.models['general'].update(features, actual_speed)
        
        # به‌روزرسانی مدل کاربر
        if user_id:
            await self._update_user_profile(user_id, features, actual_speed)
            await self.models['user_specific'].update(features, actual_speed)
        
        # به‌روزرسانی مدل تخصصی
        if features.file_type and features.file_type in self.models:
            await self.models[features.file_type].update(features, actual_speed)
        
        # به‌روزرسانی تشخیص الگو
        await self.pattern_detector.record_transfer(user_id, features, actual_speed)
        
        # به‌روزرسانی anomaly detection
        await self.anomaly_detector.record_data(features, actual_speed)
    
    async def _update_user_profile(self, user_id: str, features: PredictionFeatures, actual_speed: float):
        """به‌روزرسانی پروفایل کاربر"""
        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = {
                'transfer_count': 0,
                'total_speed': 0,
                'avg_speed': 0,
                'last_update': time.time(),
                'has_enough_data': False
            }
        
        profile = self.user_profiles[user_id]
        profile['transfer_count'] += 1
        profile['total_speed'] += actual_speed
        profile['avg_speed'] = profile['total_speed'] / profile['transfer_count']
        profile['last_update'] = time.time()
        
        if profile['transfer_count'] >= 10:
            profile['has_enough_data'] = True
    
    async def get_optimization_recommendations(
        self,
        transfer_id: str,
        context: Dict[str, Any],
        network_analysis: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """دریافت توصیه‌های بهینه‌سازی"""
        recommendations = []
        
        # تحلیل شبکه
        if network_analysis.get('latency', 0) > 100:
            recommendations.append({
                'type': 'network',
                'action': 'reduce_connections',
                'reason': 'High latency detected',
                'priority': 'high',
                'estimated_improvement': '20-30%'
            })
        
        if network_analysis.get('packet_loss', 0) > 0.05:
            recommendations.append({
                'type': 'network',
                'action': 'enable_fec',
                'reason': 'High packet loss',
                'priority': 'high',
                'estimated_improvement': '15-25%'
            })
        
        # تحلیل فایل
        file_size = context.get('file_size', 0)
        if file_size > 100 * 1024 * 1024:
            recommendations.append({
                'type': 'file',
                'action': 'enable_resume',
                'reason': 'Large file size',
                'priority': 'medium',
                'estimated_improvement': 'Prevent restart on failure'
            })
        
        # تحلیل تاریخی
        user_id = context.get('user_id')
        if user_id and user_id in self.user_profiles:
            profile = self.user_profiles[user_id]
            if profile['avg_speed'] < 5:  # کاربر با سرعت پایین
                recommendations.append({
                    'type': 'user',
                    'action': 'enable_compression',
                    'reason': 'User has historically low speeds',
                    'priority': 'medium',
                    'estimated_improvement': '30-50% bandwidth savings'
                })
        
        return recommendations
    
    async def predict_future_speed(self, speed_samples: List[float]) -> float:
        """پیش‌بینی سرعت آینده بر اساس نمونه‌های اخیر"""
        if not speed_samples:
            return 0
        
        # استفاده از میانگین متحرک با وزن نمایی
        weights = np.exp(np.linspace(-1, 0, len(speed_samples)))
        weights /= weights.sum()
        
        return float(np.dot(speed_samples, weights))
    
    async def get_performance_report(self) -> Dict[str, Any]:
        """گزارش عملکرد مدل‌های AI"""
        report = {
            'total_models': len(self.models),
            'user_profiles': len(self.user_profiles),
            'model_performance': {},
            'timestamp': time.time()
        }
        
        for name, model in self.models.items():
            report['model_performance'][name] = {
                'training_samples': len(model.training_data),
                'last_trained': model.last_trained,
                'version': model.model_version
            }
        
        return report
    
    async def shutdown(self):
        """خاموش کردن graceful"""
        logger.info("Shutting down AISpeedPredictor...")
        
        # ذخیره مدل‌ها
        for name, model in self.models.items():
            try:
                await model._save_model()
            except:
                pass
        
        # ذخیره پروفایل کاربران
        await self._save_user_profiles()
        
        logger.info("AISpeedPredictor shutdown complete")
    
    async def _save_user_profiles(self):
        """ذخیره پروفایل کاربران"""
        try:
            profiles_dir = Path("user_profiles")
            profiles_dir.mkdir(exist_ok=True)
            
            profiles_file = profiles_dir / "profiles.json"
            with open(profiles_file, 'w') as f:
                json.dump(self.user_profiles, f, indent=2)
            
            logger.info(f"User profiles saved to {profiles_file}")
            
        except Exception as e:
            logger.error(f"Failed to save user profiles: {e}")

class PatternDetector:
    """تشخیص الگوهای زمانی و رفتاری"""
    
    def __init__(self):
        self.user_patterns: Dict[str, Dict] = defaultdict(dict)
        self.time_windows = {
            'hourly': 24,
            'daily': 7,
            'weekly': 4
        }
    
    async def detect_time_pattern(self, user_id: Optional[str]) -> Optional[Dict]:
        """تشخیص الگوهای زمانی کاربر"""
        if not user_id or user_id not in self.user_patterns:
            return None
        
        patterns = self.user_patterns[user_id]
        current_hour = datetime.now().hour
        current_day = datetime.now().weekday()
        
        # بررسی الگوهای ساعتی
        if 'hourly' in patterns:
            hour_pattern = patterns['hourly'].get(current_hour)
            if hour_pattern:
                return {
                    'type': 'hourly',
                    'speed_factor': hour_pattern.get('avg_speed', 1.0),
                    'confidence': hour_pattern.get('confidence', 0.5)
                }
        
        # بررسی الگوهای روزانه
        if 'daily' in patterns:
            day_pattern = patterns['daily'].get(current_day)
            if day_pattern:
                return {
                    'type': 'daily',
                    'speed_factor': day_pattern.get('avg_speed', 1.0),
                    'confidence': day_pattern.get('confidence', 0.5)
                }
        
        return None
    
    async def record_transfer(self, user_id: str, features: PredictionFeatures, actual_speed: float):
        """ثبت انتقال برای تشخیص الگو"""
        if not user_id:
            return
        
        if user_id not in self.user_patterns:
            self.user_patterns[user_id] = {
                'hourly': defaultdict(list),
                'daily': defaultdict(list),
                'weekly': defaultdict(list),
                'total_transfers': 0
            }
        
        patterns = self.user_patterns[user_id]
        
        # ثبت بر اساس ساعت
        hour = features.time_of_day
        patterns['hourly'][hour].append(actual_speed)
        
        # ثبت بر اساس روز هفته
        day = features.day_of_week
        patterns['daily'][day].append(actual_speed)
        
        patterns['total_transfers'] += 1
        
        # محاسبه میانگین‌ها
        self._calculate_patterns(user_id)
    
    def _calculate_patterns(self, user_id: str):
        """محاسبه الگوها از داده‌های ثبت شده"""
        patterns = self.user_patterns[user_id]
        
        for period in ['hourly', 'daily', 'weekly']:
            for key, speeds in patterns[period].items():
                if len(speeds) >= 3:  # حداقل 3 نمونه
                    avg_speed = statistics.mean(speeds)
                    std_dev = statistics.stdev(speeds) if len(speeds) > 1 else 0
                    
                    patterns[period][key] = {
                        'avg_speed': avg_speed,
                        'std_dev': std_dev,
                        'samples': len(speeds),
                        'confidence': min(1.0, len(speeds) / 10)  # confidence بر اساس تعداد نمونه‌ها
                    }

class AnomalyDetector:
    """تشخیص anomalies در داده‌های سرعت"""
    
    def __init__(self):
        self.historical_data = deque(maxlen=1000)
        self.threshold_multiplier = 3.0  # ضریب برای تشخیص outlier
    
    async def is_anomaly(self, features: PredictionFeatures, predicted_speed: float) -> bool:
        """بررسی anomaly بودن پیش‌بینی"""
        if not self.historical_data:
            return False
        
        # یافتن داده‌های مشابه تاریخی
        similar_speeds = []
        for hist_features, hist_speed in self.historical_data:
            if self._are_features_similar(features, hist_features):
                similar_speeds.append(hist_speed)
        
        if not similar_speeds:
            return False
        
        # محاسبه آمار
        mean_speed = statistics.mean(similar_speeds)
        std_speed = statistics.stdev(similar_speeds) if len(similar_speeds) > 1 else 0
        
        if std_speed == 0:
            return abs(predicted_speed - mean_speed) > mean_speed * 0.5  # 50% تفاوت
        
        # محاسبه z-score
        z_score = abs(predicted_speed - mean_speed) / std_speed
        
        return z_score > self.threshold_multiplier
    
    def _are_features_similar(self, f1: PredictionFeatures, f2: PredictionFeatures) -> bool:
        """بررسی شباهت ویژگی‌ها"""
        # بررسی نوع شبکه
        if f1.network_type != f2.network_type:
            return False
        
        # بررسی محدوده زمانی
        if abs(f1.time_of_day - f2.time_of_day) > 2:  # بیش از 2 ساعت تفاوت
            return False
        
        # بررسی محدوده حجم فایل
        size_ratio = max(f1.file_size, f2.file_size) / min(f1.file_size, f2.file_size)
        if size_ratio > 10:  # بیش از 10 برابر تفاوت
            return False
        
        return True
    
    async def record_data(self, features: PredictionFeatures, actual_speed: float):
        """ثبت داده برای anomaly detection"""
        self.historical_data.append((features, actual_speed))

# Singleton instance
ai_predictor = AISpeedPredictor()
