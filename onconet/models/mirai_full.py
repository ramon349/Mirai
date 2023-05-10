from onconet.models.factory import load_model, RegisterModel, get_model_by_name
import math
import torch
import torch.nn as nn
import pdb
import numpy as np 
from collections import defaultdict 
activation=defaultdict(list) 
@RegisterModel("mirai_full")
class MiraiFull(nn.Module):
    def __init__(self, args):
        super(MiraiFull, self).__init__()
        self.args = args
        if args.img_encoder_snapshot is not None:
            self.image_encoder = load_model(args.img_encoder_snapshot, args, do_wrap_model=False)
        else:
            self.image_encoder = get_model_by_name('custom_resnet', False, args)

        if hasattr(self.args, "freeze_image_encoder") and self.args.freeze_image_encoder:
            for param in self.image_encoder.parameters():
                param.requires_grad = False

        self.image_repr_dim = self.image_encoder._model.args.img_only_dim
        if args.transformer_snapshot is not None:
            self.transformer = load_model(args.transformer_snapshot, args, do_wrap_model=False)
        else:
            args.precomputed_hidden_dim = self.image_repr_dim
            self.transformer = get_model_by_name('transformer', False, args)
        args.img_only_dim = self.transformer.args.transfomer_hidden_dim

    def forward(self, x, risk_factors=None, batch=None):
        B, C, N, H, W = x.size()
        pdb.set_trace()
        x = x.transpose(1,2).contiguous().view(B*N, C, H, W)
        risk_factors_per_img =  (lambda N, risk_factors: [factor.expand( [N, *factor.size()]).contiguous().view([-1, factor.size()[-1]]).contiguous() for factor in risk_factors])(N, risk_factors) if risk_factors is not None else None
        _, img_x, _ = self.image_encoder(x, risk_factors_per_img, batch)
        img_x = img_x.view(B, N, -1)
        img_x = img_x[:,:,: self.image_repr_dim]
        logit, transformer_hidden, activ_dict = self.transformer(img_x, risk_factors, batch)
        return logit, transformer_hidden, activ_dict

def getActivation(name):
    # the hook signature
    def hook(model, args ,outputs):
        activation[name].append(outputs.cpu().numpy().mean().mean().mean())
    return hook
@RegisterModel("mirai_full_debias")
class MiraiFullDebias(nn.Module):
    def __init__(self, args):
        super(MiraiFullDebias, self).__init__()
        self.args = args
        if args.img_encoder_snapshot is not None:
            self.image_encoder = load_model(args.img_encoder_snapshot, args, do_wrap_model=False)
        else:
            self.image_encoder = get_model_by_name('custom_resnet', False, args)
        if hasattr(self.args, "freeze_image_encoder") and self.args.freeze_image_encoder:
            for param in self.image_encoder.parameters():
                param.requires_grad = False
        self.image_repr_dim = self.image_encoder._model.args.img_only_dim
        if args.transformer_snapshot is not None:
            self.transformer = load_model(args.transformer_snapshot, args, do_wrap_model=False)
        else:
            args.precomputed_hidden_dim = self.image_repr_dim
            self.transformer = get_model_by_name('transformer', False, args)
        args.img_only_dim = self.transformer.args.transfomer_hidden_dim
        self.bias_classi = nn.Sequential(
            nn.Linear(args.img_only_dim,512),
            nn.ReLU(), 
            nn.Linear(512,3)
        ) 
        self.transformer.transformer.transformer_layer_0.multihead_attention.query.register_forward_hook(getActivation('query')) 

    def forward(self, x, risk_factors=None, batch=None):
        B, C, N, H, W = x.size() 
        pdb.set_trace()
        x = x.transpose(1,2).contiguous().view(B*N, C, H, W)
        risk_factors_per_img =  (lambda N, risk_factors: [factor.expand( [N, *factor.size()]).contiguous().view([-1, factor.size()[-1]]).contiguous() for factor in risk_factors])(N, risk_factors) if risk_factors is not None else None
        _, img_x, _ = self.image_encoder(x, risk_factors_per_img, batch)
        img_x = img_x.view(B, N, -1)
        img_x = img_x[:,:,: self.image_repr_dim]
        logit, transformer_hidden, activ_dict = self.transformer(img_x, risk_factors, batch)
        activ_dict['bias_classi'] = self.bias_classi(logit)
        activ_dict['query_acti'] = activation['query']
        return logit, transformer_hidden, activ_dict
