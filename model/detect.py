from ultralytics import YOLO
import cv2
import os

class OilSpillDetector:
    def __init__(self, model_path, conf=0.3):
        self.model = YOLO(model_path)
        self.conf = conf

    def predict(self, image_path, prediction_dir):
        os.makedirs(prediction_dir, exist_ok=True)

        results = self.model(image_path, conf=self.conf)

        detected = False
        confidence = 0.0
        output_filename = None

        for r in results:
            if len(r.boxes) > 0:
                detected = True
                confidence = float(r.boxes.conf.max())

            annotated_img = r.plot()

            output_filename = "pred_" + os.path.basename(image_path)
            output_path = os.path.join(prediction_dir, output_filename)
            cv2.imwrite(output_path, annotated_img)

        return detected, confidence, output_filename
