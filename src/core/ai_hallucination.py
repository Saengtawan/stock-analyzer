"""
AI Hallucination Detector
Detects and filters AI-generated data that contradicts real data
"""
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class HallucinationDetection:
    """Result of hallucination detection"""
    field: str
    is_hallucination: bool
    confidence: float  # 0-1
    ai_value: Any
    real_value: Any
    discrepancy_percentage: Optional[float] = None
    severity: str = "low"  # low, medium, high, critical

    def to_dict(self) -> Dict[str, Any]:
        return {
            'field': self.field,
            'is_hallucination': self.is_hallucination,
            'confidence': round(self.confidence, 2),
            'ai_value': self.ai_value,
            'real_value': self.real_value,
            'discrepancy_percentage': round(self.discrepancy_percentage, 2) if self.discrepancy_percentage else None,
            'severity': self.severity,
            'action': 'use_real_value' if self.is_hallucination else 'use_ai_value'
        }


class AIHallucinationDetector:
    """Detects AI hallucinations by cross-checking with real data"""

    # Thresholds for different field types
    THRESHOLDS = {
        'price': {'tolerance': 0.05},  # 5% tolerance
        'pe_ratio': {'tolerance': 0.50},  # 50% tolerance (P/E can vary)
        'pb_ratio': {'tolerance': 0.30},
        'market_cap': {'tolerance': 0.10},
        'revenue': {'tolerance': 0.15},
        'earnings': {'tolerance': 0.20},
        'roe': {'tolerance': 0.25},
        'roa': {'tolerance': 0.25},
        'profit_margin': {'tolerance': 0.20},
        'debt_to_equity': {'tolerance': 0.30}
    }

    def __init__(self, strict_mode: bool = False):
        """
        Initialize hallucination detector

        Args:
            strict_mode: If True, use stricter thresholds
        """
        self.strict_mode = strict_mode
        if strict_mode:
            # Reduce all tolerances by 50% in strict mode
            self.thresholds = {
                k: {'tolerance': v['tolerance'] * 0.5}
                for k, v in self.THRESHOLDS.items()
            }
        else:
            self.thresholds = self.THRESHOLDS.copy()

    def detect_hallucinations(
        self,
        ai_data: Dict[str, Any],
        real_data: Dict[str, Any]
    ) -> List[HallucinationDetection]:
        """
        Detect hallucinations by comparing AI data with real data

        Args:
            ai_data: AI-generated data
            real_data: Real data from APIs

        Returns:
            List of hallucination detections
        """
        detections = []

        # Check each field in AI data
        for field, ai_value in ai_data.items():
            if field not in real_data:
                continue  # Can't verify without real data

            real_value = real_data[field]

            # Skip if either is None
            if ai_value is None or real_value is None:
                continue

            detection = self._check_field(field, ai_value, real_value)
            if detection:
                detections.append(detection)

        return detections

    def _check_field(
        self,
        field: str,
        ai_value: Any,
        real_value: Any
    ) -> Optional[HallucinationDetection]:
        """
        Check a single field for hallucination

        Args:
            field: Field name
            ai_value: AI-generated value
            real_value: Real value

        Returns:
            HallucinationDetection or None
        """
        # Handle numeric fields
        if isinstance(ai_value, (int, float)) and isinstance(real_value, (int, float)):
            return self._check_numeric_field(field, float(ai_value), float(real_value))

        # Handle string fields
        elif isinstance(ai_value, str) and isinstance(real_value, str):
            return self._check_string_field(field, ai_value, real_value)

        # Handle boolean fields
        elif isinstance(ai_value, bool) and isinstance(real_value, bool):
            return self._check_boolean_field(field, ai_value, real_value)

        return None

    def _check_numeric_field(
        self,
        field: str,
        ai_value: float,
        real_value: float
    ) -> Optional[HallucinationDetection]:
        """Check numeric field for hallucination"""

        # Avoid division by zero
        if real_value == 0:
            if ai_value == 0:
                return None  # Both zero, no hallucination
            else:
                # Real is zero but AI is not - hallucination
                return HallucinationDetection(
                    field=field,
                    is_hallucination=True,
                    confidence=0.95,
                    ai_value=ai_value,
                    real_value=real_value,
                    severity='high'
                )

        # Calculate percentage difference
        diff = abs(ai_value - real_value)
        percent_diff = diff / abs(real_value)

        # Get threshold for this field
        threshold = self.thresholds.get(field, {'tolerance': 0.20})['tolerance']

        is_hallucination = percent_diff > threshold

        # Determine severity
        if percent_diff > threshold * 3:
            severity = 'critical'
        elif percent_diff > threshold * 2:
            severity = 'high'
        elif percent_diff > threshold * 1.5:
            severity = 'medium'
        else:
            severity = 'low'

        # Confidence based on how far off it is
        confidence = min(0.99, percent_diff / threshold) if is_hallucination else 0.10

        return HallucinationDetection(
            field=field,
            is_hallucination=is_hallucination,
            confidence=confidence,
            ai_value=ai_value,
            real_value=real_value,
            discrepancy_percentage=percent_diff * 100,
            severity=severity
        )

    def _check_string_field(
        self,
        field: str,
        ai_value: str,
        real_value: str
    ) -> Optional[HallucinationDetection]:
        """Check string field for hallucination"""

        is_match = ai_value.lower().strip() == real_value.lower().strip()

        if not is_match:
            return HallucinationDetection(
                field=field,
                is_hallucination=True,
                confidence=0.90,
                ai_value=ai_value,
                real_value=real_value,
                severity='medium'
            )

        return None

    def _check_boolean_field(
        self,
        field: str,
        ai_value: bool,
        real_value: bool
    ) -> Optional[HallucinationDetection]:
        """Check boolean field for hallucination"""

        if ai_value != real_value:
            return HallucinationDetection(
                field=field,
                is_hallucination=True,
                confidence=1.0,
                ai_value=ai_value,
                real_value=real_value,
                severity='high'
            )

        return None

    def merge_data_with_verification(
        self,
        ai_data: Dict[str, Any],
        real_data: Dict[str, Any],
        prefer_real: bool = True
    ) -> Tuple[Dict[str, Any], List[HallucinationDetection]]:
        """
        Merge AI and real data, preferring real data when hallucinations detected

        Args:
            ai_data: AI-generated data
            real_data: Real data
            prefer_real: If True, always prefer real data when available

        Returns:
            (merged_data, detections)
        """
        detections = self.detect_hallucinations(ai_data, real_data)

        merged = ai_data.copy()

        # Replace hallucinated fields with real data
        for detection in detections:
            if detection.is_hallucination or prefer_real:
                merged[detection.field] = detection.real_value
                logger.info(
                    f"Replaced AI value for {detection.field} with real data",
                    extra={
                        'field': detection.field,
                        'ai_value': detection.ai_value,
                        'real_value': detection.real_value,
                        'discrepancy': detection.discrepancy_percentage
                    }
                )

        return merged, detections

    def get_hallucination_report(
        self,
        detections: List[HallucinationDetection]
    ) -> Dict[str, Any]:
        """
        Generate hallucination report

        Args:
            detections: List of detections

        Returns:
            Report dictionary
        """
        hallucinations = [d for d in detections if d.is_hallucination]

        severity_counts = {
            'critical': sum(1 for d in hallucinations if d.severity == 'critical'),
            'high': sum(1 for d in hallucinations if d.severity == 'high'),
            'medium': sum(1 for d in hallucinations if d.severity == 'medium'),
            'low': sum(1 for d in hallucinations if d.severity == 'low')
        }

        return {
            'total_fields_checked': len(detections),
            'hallucinations_detected': len(hallucinations),
            'hallucination_rate': len(hallucinations) / len(detections) if detections else 0,
            'severity_breakdown': severity_counts,
            'detections': [d.to_dict() for d in hallucinations],
            'recommendation': self._get_recommendation(hallucinations)
        }

    @staticmethod
    def _get_recommendation(hallucinations: List[HallucinationDetection]) -> str:
        """Get recommendation based on hallucinations"""
        if not hallucinations:
            return "No hallucinations detected. AI data is reliable."

        critical = sum(1 for h in hallucinations if h.severity == 'critical')
        high = sum(1 for h in hallucinations if h.severity == 'high')

        if critical > 0:
            return "Critical hallucinations detected. Use real data only."
        elif high > 2:
            return "Multiple high-severity hallucinations. Prefer real data."
        elif len(hallucinations) > 5:
            return "Many hallucinations detected. AI data may be unreliable."
        else:
            return "Minor hallucinations detected. Proceed with caution."
