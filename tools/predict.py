# -*- coding: utf-8 -*-
# @File  : predict.py
# @Author: yblir
# @Time  : 2024/2/21 23:13
# @Explain: 
# ======================================================================================================================
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import argparse
import numpy as np

from src.core import YAMLConfig

import torch
import torch.nn as nn


def main(args, ):
    """main
    """
    cfg = YAMLConfig(args.config, resume=args.resume)

    if args.resume:
        checkpoint = torch.load(args.resume, map_location='cpu')
        if 'ema' in checkpoint:
            state = checkpoint['ema']['module']
        else:
            state = checkpoint['model']
    else:
        raise AttributeError('only support resume to load model.state_dict by now.')

    # NOTE load train mode state -> convert to deploy mode
    cfg.model.load_state_dict(state)

    class Model(nn.Module):
        def __init__(self, ) -> None:
            super().__init__()
            self.model = cfg.model.deploy()
            self.postprocessor = cfg.postprocessor.deploy()
            print(self.postprocessor.deploy_mode)

        def forward(self, images, orig_target_sizes):
            outputs = self.model(images)
            return self.postprocessor(outputs, orig_target_sizes)

    model = Model()

    dynamic_axes = {
        'images': {0: 'N', },
        'orig_target_sizes': {0: 'N'}
    }

    data = torch.rand(1, 3, 640, 640)
    size = torch.tensor([[640, 640]])

    torch.onnx.export(
        model,
        (data, size),
        args.file_name,
        input_names=['images', 'orig_target_sizes'],
        output_names=['labels', 'boxes', 'scores'],
        dynamic_axes=dynamic_axes,
        opset_version=16,
        verbose=False
    )

    if args.check:
        import onnx
        onnx_model = onnx.load(args.file_name)
        onnx.checker.check_model(onnx_model)
        print('Check export onnx model done...')

    if args.simplify:
        import onnxsim
        dynamic = True
        input_shapes = {'images': data.shape, 'orig_target_sizes': size.shape} if dynamic else None
        onnx_model_simplify, check = onnxsim.simplify(args.file_name, input_shapes=input_shapes,
                                                      dynamic_input_shape=dynamic)
        onnx.save(onnx_model_simplify, args.file_name)
        print(f'Simplify onnx model {check}...')

    import onnxruntime as ort
    from PIL import Image, ImageDraw
    from torchvision.transforms import ToTensor

    # print(onnx.helper.printable_graph(mm.graph))

    im = Image.open(r'E:\localDatasets\coco_DETR\val2017\000000001000.jpg').convert('RGB')
    im = im.resize((640, 640))
    im_data = ToTensor()(im)[None]
    print(im_data.shape)

    sess = ort.InferenceSession(args.file_name)
    output = sess.run(
        # output_names=['labels', 'boxes', 'scores'],
        output_names=None,
        input_feed={'images': im_data.data.numpy(), "orig_target_sizes": size.data.numpy()}
    )

    # print(type(output))
    # print([out.shape for out in output])

    labels, boxes, scores = output

    draw = ImageDraw.Draw(im)
    thrh = 0.6

    for i in range(im_data.shape[0]):

        scr = scores[i]
        lab = labels[i][scr > thrh]
        box = boxes[i][scr > thrh]

        print(i, sum(scr > thrh))

        for b in box:
            draw.rectangle(list(b), outline='red',)
            draw.text((b[0], b[1]), text=str(lab[i]), fill='blue', )

    im.save('test.jpg')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', '-c', default="../configs/rtdetr/rtdetr_r50vd_6x_coco.yml", type=str, )
    parser.add_argument('--resume', '-r', default="../weight/rtdetr_r50vd_6x_coco_from_paddle.pth", type=str, )
    parser.add_argument('--file-name', '-f', type=str, default='model.onnx')
    parser.add_argument('--check', action='store_true', default=False, )
    parser.add_argument('--simplify', action='store_true', default=False, )

    args = parser.parse_args()

    main(args)
