import torch
from torch.autograd import Variable
import torch.optim as optim
import torch.nn.functional as F
from network import *
from module_bruit import F_bruit, Patch_block, Sup_res1, Sup_res2, Sup_res3
import torchvision.transforms as transforms
from utils import *

from sacred import Experiment
from sacred.observers import MongoObserver

from tqdm import tqdm
from dataset import MiniCelebADataset, CelebADataset, CelebADatasetSup

ex = Experiment('test')
#ex.observers.append(MongoObserver.create(url='mongodb://besnier:XXXXX@drunk',db_name='VictorSacred'))

@ex.config
def conf():
    device = 'cuda:0'
    netG = NetG_super().to(device)
    netD = NetD_super().to(device)
    optimizerG = optim.Adam(netG.parameters(), 0.0002, betas=(0.5, 0.999))
    optimizerD = optim.Adam(netD.parameters(), 0.0001, betas=(0.5, 0.999))
    f_bruit = Sup_res1
    epoch = 100
    cuda = True
    param = None
    f = f_bruit(param)

    trainset = MiniCelebADataset("/local/besnier/visage/miniCelebA_64",
                                 "/local/besnier/visage/mini_idTrain.txt",
                                 f,
                                 transforms.Compose([transforms.ToTensor(),
                                                     transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
                                                     ]))

    testset = MiniCelebADataset("/local/besnier/visage/miniCelebA_64",
                                "/local/besnier/visage/mini_idTest.txt",
                                f,
                                transforms.Compose([transforms.ToTensor(),
                                                    transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
                                                    ]))
    trainloader = torch.utils.data.DataLoader(trainset, batch_size=64, shuffle=True, num_workers=4, drop_last=True)
    testloader = torch.utils.data.DataLoader(testset, batch_size=64, shuffle=True, num_workers=4, drop_last=True)

    dataset = CelebADatasetSup("/local/besnier/img_align_celeba",
                               f,
                               transforms.Compose([transforms.Resize(64),
                                                   transforms.ToTensor(),
                                                   transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
                                                   ]))

    dataloader = torch.utils.data.DataLoader(dataset, batch_size=64, shuffle=True, num_workers=1, drop_last=True)


@ex.automain
def main(netG, netD, f_bruit, epoch, param, cuda, dataloader, optimizerG, optimizerD):
    netG.train()
    netD.train()
    sauvegarde_init()
    cpt = 0
    dTrue = []
    dFalse = []
    mse = []
    ref = []
    module_bruit = f_bruit(param)
    if cuda:
        module_bruit.cuda()
    turn = True
    bar_epoch = tqdm(range(epoch))
    for _ in bar_epoch:
        for i, (x, x2, xb, xb2) in zip(tqdm(range(len(dataloader))), dataloader):
            if turn:
                save_xb = xb
                print_img(save_xb, 'image_de_base_bruit')
                print_img(x, 'image_de_base_sans_bruit')
                turn = False
                if cuda:
                    save_xb = save_xb.cuda()

            real_label = torch.FloatTensor(x.size(0)).fill_(.9)
            fake_label = torch.FloatTensor(x.size(0)).fill_(.1)

            if cuda:
                real_label = real_label.cuda()
                fake_label = fake_label.cuda()
                xb = xb.cuda()
                x = x.cuda()
                x2 = x2.cuda()

            # train D
            optimizerD.zero_grad()

            # avec de vrais labels
            outputTrue = netD(xb)
            lossDT = F.binary_cross_entropy_with_logits(outputTrue, real_label)

            # avec de faux labels
            fake = module_bruit(netG(xb), b=True)
            outputFalse = netD(fake)
            lossDF = F.binary_cross_entropy_with_logits(outputFalse, fake_label)
            (lossDF + lossDT).backward()
            optimizerD.step()

            # train G

            optimizerG.zero_grad()
            outputG = module_bruit(netG(xb), b=True)
            outputDbruit = netD(outputG)
            lossBruit = F.binary_cross_entropy_with_logits(outputDbruit, real_label)

            lossBruit.backward()
            optimizerG.step()

            #test
            dTrue.append(F.sigmoid(outputTrue).data.mean())
            dFalse.append(F.sigmoid(outputFalse).data.mean())
            mse.append(F.mse_loss(netG(xb).detach(), x))
            ref.append(F.mse_loss(x2, x))

            bar_epoch.set_postfix({"Dataset": np.array(dTrue).mean(),
                                   "G": np.array(dFalse).mean(),
                                   "qualité": np.array(mse).mean(),
                                   "ref": np.array(ref).mean()})

            sauvegarde(np.array(dTrue).mean(), np.array(dFalse).mean(), np.array(mse).mean(), np.array(ref).mean())

            if i % 250 == 0:
                printG(save_xb, cpt, netG)
                cpt += 1
                dTrue = []
                dFalse = []
                mse = []
                ref = []
